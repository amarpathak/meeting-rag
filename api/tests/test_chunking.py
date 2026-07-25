from app.chunking import chunk_turns
from app.parsing import Turn


def _turn(ts: str, speaker: str, n_words: int) -> Turn:
    return Turn(timestamp=ts, speaker=speaker, text=" ".join(["word"] * n_words))


def test_never_splits_an_oversized_turn():
    # A single turn larger than the budget must land whole in its own chunk.
    big = _turn("00:00:01", "A", 40)  # ~52 tokens, over the budget below
    chunks = chunk_turns([big], target_tokens=25, overlap_turns=1)
    assert len(chunks) == 1
    assert chunks[0].content.count("word") == 40  # the whole turn, intact


def test_packs_consecutive_turns_to_budget():
    # ~13 tokens/turn, budget 30: two fit, a third would overflow → two per chunk.
    turns = [_turn(f"00:00:0{i}", "A", 10) for i in range(1, 5)]
    chunks = chunk_turns(turns, target_tokens=30, overlap_turns=0)
    assert len(chunks) == 2
    assert (chunks[0].ts_start, chunks[0].ts_end) == ("00:00:01", "00:00:02")
    assert (chunks[1].ts_start, chunks[1].ts_end) == ("00:00:03", "00:00:04")


def test_overlap_carries_the_boundary_turn():
    turns = [_turn(f"00:00:0{i}", "A", 10) for i in range(1, 5)]
    chunks = chunk_turns(turns, target_tokens=30, overlap_turns=1)
    # With one-turn overlap, each chunk ends on the turn the next chunk begins with.
    for earlier, later in zip(chunks, chunks[1:]):
        assert earlier.ts_end == later.ts_start
