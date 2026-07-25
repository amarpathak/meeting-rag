import re
from dataclasses import dataclass, field

# A turn line looks like:  [00:01:22] Tom Whelan: Topline first...
# Timestamp is HH:MM:SS or MM:SS; speaker is everything up to the first colon.
_TURN_RE = re.compile(
    r"^\[(?P<ts>\d{1,2}:\d{2}(?::\d{2})?)\]\s+(?P<speaker>[^:]+?):\s*(?P<text>.*)$"
)
_HEADER_RE = re.compile(r"^(?P<key>Meeting|Date|Attendees):\s*(?P<value>.+)$")


@dataclass(frozen=True)
class Turn:
    timestamp: str
    speaker: str
    text: str


@dataclass(frozen=True)
class ParsedTranscript:
    title: str | None
    date: str | None
    attendees: str | None
    turns: list[Turn] = field(default_factory=list)


def parse_transcript(raw: str) -> ParsedTranscript:
    title: str | None = None
    date: str | None = None
    attendees: str | None = None
    turns: list[Turn] = []

    for line in raw.splitlines():
        line = line.rstrip()
        if not line:
            continue

        turn_match = _TURN_RE.match(line)
        if turn_match:
            turns.append(
                Turn(
                    timestamp=turn_match["ts"],
                    speaker=turn_match["speaker"].strip(),
                    text=turn_match["text"].strip(),
                )
            )
            continue

        header_match = _HEADER_RE.match(line)
        if header_match:
            key, value = header_match["key"], header_match["value"].strip()
            if key == "Meeting":
                title = value
            elif key == "Date":
                date = value
            elif key == "Attendees":
                attendees = value
            continue

        # A line that is neither header nor a new turn is a continuation of the
        # previous speaker's utterance (multi-line turns). Append rather than
        # drop it, so no spoken content is silently lost.
        if turns:
            last = turns[-1]
            turns[-1] = Turn(last.timestamp, last.speaker, f"{last.text} {line.strip()}")

    return ParsedTranscript(title=title, date=date, attendees=attendees, turns=turns)
