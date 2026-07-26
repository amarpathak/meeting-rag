from dataclasses import dataclass


@dataclass(frozen=True)
class EvalQuestion:
    question: str
    should_answer: bool
    # For answerable questions: a fact that must appear in the retrieved chunks
    # if retrieval did its job. None for off-topic questions.
    expect_contains: str | None = None


@dataclass(frozen=True)
class EvalSet:
    name: str
    # Matched against transcript title/filename to scope retrieval. Without this
    # every set searched every meeting, so recall and the floor sweep were both
    # measured against chunks from transcripts the question was never about.
    transcript_match: str
    questions: list[EvalQuestion]
    # Where the transcript comes from, for sets whose meeting is not bundled in
    # data/. Without it a fresh clone runs one set, skips the other, and the
    # reviewer has no way to know what was missing or how to get it.
    source: str = "bundled in data/transcripts"


ADVISORY_BOARD = EvalSet(
    name="advisory-board",
    transcript_match="Cardiology Advisory Board",
    questions=[
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
    ],
)

# A harder set on purpose: this transcript came from YouTube auto-captions, so it
# is lowercase, unpunctuated, has inferred speaker labels, and is 42 minutes of
# rambling discussion rather than a tight structured meeting. If retrieval holds
# up here it is not just working on clean hand-written samples.
YOUTUBE_PMM = EvalSet(
    name="youtube-pmm",
    transcript_match="Product Marketing Meeting",
    source="https://www.youtube.com/watch?v=lBVtvOpU80Q  (load it via ＋ Load meeting)",
    questions=[
        EvalQuestion("Which conference is GitOps being paired with?", True, "kubecon"),
        EvalQuestion("What sync cadence does the team currently have?", True, "two-week"),
        EvalQuestion("Why is it hard to make product announcements at GitLab?", True,
                     "roadmap is completely public"),
        EvalQuestion("Which security topic did they choose for the announcement?", True,
                     "vulnerability management"),
        EvalQuestion("Why won't they do more press on the fuzzing acquisition?", True, "fuzzing"),
        EvalQuestion("How is the excitement level of a feature decided?", True, "judgment call"),
        EvalQuestion("What metric was suggested for measuring customer interest?", True, "mau"),
        EvalQuestion("What was notable about the VS Code integrations?", True,
                     "community contributions"),
        EvalQuestion("Which planning feature had been requested for years?", True, "epic boards"),
        # Off-topic. The cardiology question is deliberate: it is answerable in a
        # different ingested meeting, so it also proves retrieval stays scoped.
        EvalQuestion("What was the hazard ratio for the primary endpoint?", False),
        EvalQuestion("What is the best recipe for chocolate chip cookies?", False),
        EvalQuestion("Who won the 2018 FIFA World Cup?", False),
        EvalQuestion("What were the patient enrollment numbers?", False),
    ],
)

SETS = [ADVISORY_BOARD, YOUTUBE_PMM]

# Kept so `from .questions import QUESTIONS` still works.
QUESTIONS = ADVISORY_BOARD.questions
