from pathlib import Path

from .db import cursor
from .ingest import content_hash, ingest_transcript
from .parsing import parse_transcript

SAMPLES_DIR = Path("/data/transcripts")


def list_samples() -> list[dict]:
    """The bundled transcripts, each with whether it is already in the library.

    These ship in the format the parser expects, so loading one is parse → chunk →
    embed with no generation call. That is worth reporting to the UI, because every
    other load path can spend one.

    `transcript_id` is resolved by content hash rather than filename: the hash is
    what ingest actually deduplicates on, so this agrees with what a second load
    would do instead of guessing.
    """
    if not SAMPLES_DIR.is_dir():
        return []

    files = sorted(SAMPLES_DIR.glob("*.txt"))
    raw = {path.name: path.read_text() for path in files}
    if not raw:
        return []

    hashes = {name: content_hash(text) for name, text in raw.items()}
    with cursor() as cur:
        cur.execute(
            "SELECT content_hash, id FROM transcripts WHERE content_hash = ANY(%s)",
            (list(hashes.values()),),
        )
        ingested = dict(cur.fetchall())

    samples = []
    for name, text in raw.items():
        parsed = parse_transcript(text)
        samples.append(
            {
                "name": name,
                "title": parsed.title or Path(name).stem,
                "date": parsed.date,
                "turns": len(parsed.turns),
                "speakers": len({turn.speaker for turn in parsed.turns}),
                "transcript_id": ingested.get(hashes[name]),
            }
        )
    return samples


def ingest_sample(name: str) -> dict:
    # `name` arrives from the query string, so it is confined to the samples
    # directory before it becomes a file read. "../../etc/passwd" resolves to a
    # different parent and is rejected here rather than served.
    path = SAMPLES_DIR / name
    if path.parent != SAMPLES_DIR or not path.is_file():
        raise ValueError(f"No bundled transcript named {name!r}.")
    return ingest_transcript(path.name, path.read_text())


def ingest_all_samples() -> list[dict]:
    return [ingest_sample(path.name) for path in sorted(SAMPLES_DIR.glob("*.txt"))]
