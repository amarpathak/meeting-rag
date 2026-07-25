from app.retrieval import retrieve

from .questions import QUESTIONS


def evaluate() -> None:
    rows = []
    for q in QUESTIONS:
        results = retrieve(q.question)
        top_sim = results[0].similarity if results else 0.0
        # Retrieval "hit" = the expected fact appears anywhere in the top-k
        # chunks we'd hand to the model, not just the single best one.
        hit = None
        if q.expect_contains is not None:
            hit = any(q.expect_contains in r.content for r in results)
        rows.append((q, top_sim, hit))

    print("=== per question ===")
    for q, top_sim, hit in rows:
        expect = "answer" if q.should_answer else "refuse"
        mark = "" if hit is None else ("  ✓ fact retrieved" if hit else "  ✗ FACT MISSED")
        print(f"  top_sim={top_sim:.4f}  expect={expect:6}{mark}  {q.question}")

    answerable = [(q, s, h) for q, s, h in rows if q.expect_contains is not None]
    recall = sum(1 for _, _, h in answerable if h)
    print(f"\nretrieval recall (fact in top-k): {recall}/{len(answerable)}")

    print("\n=== floor sweep (how many answer/refuse decisions are correct) ===")
    best_floor, best_correct = 0.0, -1
    for pct in range(30, 75, 5):
        floor = pct / 100
        correct = sum((top_sim >= floor) == q.should_answer for q, top_sim, _ in rows)
        print(f"  floor={floor:.2f}  correct={correct}/{len(rows)}")
        if correct > best_correct:
            best_floor, best_correct = floor, correct

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


if __name__ == "__main__":
    evaluate()
