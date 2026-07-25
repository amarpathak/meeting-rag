from dataclasses import dataclass


@dataclass(frozen=True)
class EvalQuestion:
    question: str
    should_answer: bool
    # For answerable questions: a fact that must appear in the retrieved chunks
    # if retrieval did its job. None for off-topic questions.
    expect_contains: str | None = None


# Grounded in data/transcripts/advisory-board-2026-03-11.txt. The answerable
# set checks retrieval recall; the off-topic set checks that the similarity
# floor refuses questions the meeting never addressed.
QUESTIONS: list[EvalQuestion] = [
    EvalQuestion("What was the hazard ratio for the primary endpoint?", True, "0.81"),
    EvalQuestion("Why is the diabetic subgroup result not being led with?", True, "underpowered"),
    EvalQuestion("How many patients enrolled against the target?", True, "4,180"),
    EvalQuestion("By when will the ESC abstract be submitted?", True, "15th May"),
    EvalQuestion("Who is drafting the reactive subgroup statement?", True, "Priya"),
    EvalQuestion("What is the MLR review timeline Sofia mentioned?", True, "four week"),
    EvalQuestion("Why does Sofia want the adjusted analysis in the core dossier?", True, "appendix"),
    # Off-topic: nothing in this cardiology advisory board answers these.
    EvalQuestion("What is the best recipe for chocolate chip cookies?", False),
    EvalQuestion("Who won the 2018 FIFA World Cup?", False),
    EvalQuestion("What were the results of the oncology trial?", False),
    EvalQuestion("What is the company's quarterly revenue?", False),
]
