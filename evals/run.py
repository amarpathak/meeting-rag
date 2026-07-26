import sys

from app.config import get_settings
from app.db import cursor
from app.retrieval import retrieve

from .questions import SETS, EvalSet


def _transcript_id(match: str) -> int | None:
    with cursor() as cur:
        cur.execute(
            "SELECT id FROM transcripts WHERE title ILIKE %s OR filename ILIKE %s ORDER BY id LIMIT 1",
            (f"%{match}%", f"%{match}%"),
        )
        row = cur.fetchone()
    return row[0] if row else None


def evaluate_set(eval_set: EvalSet) -> bool:
    transcript_id = _transcript_id(eval_set.transcript_match)
    print(f"\n{'=' * 66}\n{eval_set.name}  —  transcript_match={eval_set.transcript_match!r}")
    if transcript_id is None:
        # A skipped set must say how to unskip itself. Otherwise a fresh clone
        # silently reports half the results and looks like the numbers were made up.
        print("  SKIPPED — no matching transcript ingested.")
        print(f"  To run this set, load: {eval_set.source}")
        return False
    print(f"  scoped to transcript_id={transcript_id}\n{'=' * 66}")

    rows = []
    for q in eval_set.questions:
        results = retrieve(q.question, transcript_id)
        top_sim = results[0].similarity if results else 0.0
        # Retrieval "hit" = the expected fact appears anywhere in the top-k
        # chunks we'd hand to the model, not just the single best one.
        hit = None
        if q.expect_contains is not None:
            needle = q.expect_contains.lower()
            hit = any(needle in r.content.lower() for r in results)
        rows.append((q, top_sim, hit))

    print("=== per question ===")
    for q, top_sim, hit in rows:
        expect = "answer" if q.should_answer else "refuse"
        mark = "" if hit is None else ("  ✓ fact retrieved" if hit else "  ✗ FACT MISSED")
        print(f"  top_sim={top_sim:.4f}  expect={expect:6}{mark}  {q.question}")

    answerable = [(q, s, h) for q, s, h in rows if q.expect_contains is not None]
    recall = sum(1 for _, _, h in answerable if h)
    print(f"\nretrieval recall (fact in top-k): {recall}/{len(answerable)}")

    floor = get_settings().similarity_floor
    live = sum((top_sim >= floor) == q.should_answer for q, top_sim, _ in rows)
    print(f"decisions correct at the configured floor {floor:.2f}: {live}/{len(rows)}")

    print("\n=== floor sweep (how many answer/refuse decisions are correct) ===")
    for pct in range(30, 75, 5):
        candidate = pct / 100
        correct = sum((top_sim >= candidate) == q.should_answer for q, top_sim, _ in rows)
        flag = "  <- configured" if abs(candidate - floor) < 1e-9 else ""
        print(f"  floor={candidate:.2f}  correct={correct}/{len(rows)}{flag}")

    on_topic = [s for q, s, _ in rows if q.should_answer]
    off_topic = [s for q, s, _ in rows if not q.should_answer]
    print(f"\nweakest real answer:   {min(on_topic):.4f}")
    print(f"strongest off-topic:   {max(off_topic):.4f}")
    if min(on_topic) > max(off_topic):
        # Clean gap: put the floor in the middle for maximum margin either way.
        print(f"suggested floor (gap midpoint): {(min(on_topic) + max(off_topic)) / 2:.2f}")
    else:
        print(
            "no clean separation — a topic-adjacent question outscores the weakest\n"
            "real answer. Similarity captures topic, not referent, so the floor alone\n"
            "cannot catch these; the answering prompt must also refuse ungrounded questions."
        )
    return True


def evaluate() -> None:
    wanted = sys.argv[1] if len(sys.argv) > 1 else None
    chosen = [s for s in SETS if wanted in (None, s.name)]
    if not chosen:
        print(f"No eval set named {wanted!r}. Available: {', '.join(s.name for s in SETS)}")
        return
    for eval_set in chosen:
        evaluate_set(eval_set)


if __name__ == "__main__":
    evaluate()
