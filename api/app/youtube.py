import html
import re

import httpx
from youtube_transcript_api import YouTubeTranscriptApi

# YouTube auto-captions arrive as ~1000 fragments of 3-8 words with no speakers
# and no punctuation. Merging them into paragraph-sized blocks first cuts the
# line count ~4x and gives the normaliser enough context to infer turn changes.
_BLOCK_CHARS = 220
_BLOCK_SECONDS = 22

# A 40-minute video is ~10k words. Past this the normalise call starts risking a
# truncated response, so we cut it and say so rather than silently ingesting half.
_MAX_CHARS = 48_000

_URL_PATTERNS = [
    re.compile(r"(?:youtube\.com|youtube-nocookie\.com)/watch\?(?:.*&)?v=([\w-]{11})"),
    re.compile(r"youtu\.be/([\w-]{11})"),
    re.compile(r"(?:youtube\.com|youtube-nocookie\.com)/(?:embed|shorts|live|v)/([\w-]{11})"),
]


class YouTubeError(ValueError):
    """Raised for anything the caller should see as a 400, not a 500."""


def video_id(url: str) -> str:
    for pattern in _URL_PATTERNS:
        match = pattern.search(url or "")
        if match:
            return match.group(1)
    raise YouTubeError("That doesn't look like a YouTube video URL.")


def _timestamp(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


_TITLE_RE = re.compile(r'<meta name="title" content="([^"]+)"')

# oEmbed is the documented route but answers 401 for these requests, so the title
# comes from the watch page's own meta tag. A missing title is cosmetic — never
# let this sink an otherwise good ingest.
def _title(vid: str) -> str:
    try:
        response = httpx.get(
            f"https://www.youtube.com/watch?v={vid}",
            headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"},
            timeout=15,
            follow_redirects=True,
        )
        match = _TITLE_RE.search(response.text) if response.status_code == 200 else None
        if match:
            return html.unescape(match.group(1))
    except httpx.HTTPError:
        pass
    return f"YouTube {vid}"


def _merge(segments: list[dict]) -> list[str]:
    lines: list[str] = []
    buffer: list[str] = []
    started: float | None = None

    def flush() -> None:
        if buffer:
            lines.append(f"[{_timestamp(started or 0)}] {' '.join(buffer)}")

    for segment in segments:
        text = (segment.get("text") or "").replace("\n", " ").strip()
        if not text or text.startswith("["):  # [Music], [Applause]
            continue
        if started is None:
            started = segment["start"]
        buffer.append(text)
        long_enough = len(" ".join(buffer)) >= _BLOCK_CHARS
        stale = segment["start"] - started >= _BLOCK_SECONDS
        if long_enough or stale:
            flush()
            buffer, started = [], None
    flush()
    return lines


def fetch_youtube_captions(url: str) -> tuple[str, str, bool]:
    """Return (title, timestamped caption text, whether it was truncated)."""
    vid = video_id(url)
    try:
        fetched = YouTubeTranscriptApi().fetch(vid)
    except Exception as exc:  # the library raises many distinct subclasses
        raise YouTubeError(
            f"Could not fetch captions for this video ({type(exc).__name__}). "
            "It may have captions disabled, be private, or be age-restricted."
        ) from exc

    lines = _merge(fetched.to_raw_data())
    if not lines:
        raise YouTubeError("This video has no usable caption text.")

    text = "\n".join(lines)
    truncated = len(text) > _MAX_CHARS
    if truncated:
        text = text[:_MAX_CHARS].rsplit("\n", 1)[0]
    return _title(vid), text, truncated
