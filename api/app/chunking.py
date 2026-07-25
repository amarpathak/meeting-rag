from dataclasses import dataclass

from .parsing import Turn

# The embedding cost of an exact tokenizer isn't worth it here: chunk_target is a
# soft packing target, not a billing figure. English runs ~1.3 tokens per word,
# so a word count scaled by that is close enough to decide "start a new chunk?".
_TOKENS_PER_WORD = 1.3


def estimate_tokens(text: str) -> int:
    return round(len(text.split()) * _TOKENS_PER_WORD)


@dataclass(frozen=True)
class Chunk:
    index: int
    content: str
    speakers: list[str]
    ts_start: str
    ts_end: str
    token_count: int


def _render(turns: list[Turn]) -> str:
    # Speaker and timestamp are kept inline in the embedded text, not just in
    # metadata, so a query like "what did Sofia say about MLR" can match on the
    # name, and the model sees attribution when it writes citations.
    return "\n".join(f"[{t.timestamp}] {t.speaker}: {t.text}" for t in turns)


def _build(index: int, turns: list[Turn]) -> Chunk:
    speakers: list[str] = []
    for t in turns:  # preserve first-appearance order, drop duplicates
        if t.speaker not in speakers:
            speakers.append(t.speaker)
    content = _render(turns)
    return Chunk(
        index=index,
        content=content,
        speakers=speakers,
        ts_start=turns[0].timestamp,
        ts_end=turns[-1].timestamp,
        token_count=estimate_tokens(content),
    )


def chunk_turns(
    turns: list[Turn], target_tokens: int, overlap_turns: int
) -> list[Chunk]:
    chunks: list[Chunk] = []
    current: list[Turn] = []
    current_tokens = 0

    for turn in turns:
        turn_tokens = estimate_tokens(turn.text)

        # The `current and` guard is what enforces the atomic-turn rule: an empty
        # chunk is never closed, so a single turn larger than target_tokens still
        # lands whole in its own chunk instead of being split.
        if current and current_tokens + turn_tokens > target_tokens:
            chunks.append(_build(len(chunks), current))
            current = current[-overlap_turns:] if overlap_turns else []
            current_tokens = sum(estimate_tokens(t.text) for t in current)

        current.append(turn)
        current_tokens += turn_tokens

    if current:
        chunks.append(_build(len(chunks), current))

    return chunks
