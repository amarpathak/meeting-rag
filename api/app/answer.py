import time

from google import genai
from google.genai import types

from .config import get_settings
from .db import cursor
from .prompts import ANSWER_SYSTEM_PROMPT, build_answer_prompt
from .retrieval import retrieve

# Approximate gemini-2.5-flash pricing (USD per token); update if pricing moves.
# We record cost on every call — the CLAUDE.md "no silent model calls" rule.
_INPUT_COST_PER_TOKEN = 0.30 / 1_000_000
_OUTPUT_COST_PER_TOKEN = 2.50 / 1_000_000

_client: genai.Client | None = None


def _client_() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=get_settings().gemini_api_key)
    return _client


def _log(
    question: str,
    route: str,
    answered: bool,
    top_score: float,
    chunk_ids: list[int],
    input_tokens: int | None,
    output_tokens: int | None,
    cost_usd: float,
    latency_ms: int,
) -> None:
    with cursor() as cur:
        cur.execute(
            "INSERT INTO query_log (question, route, answered, top_score, chunk_ids, "
            "input_tokens, output_tokens, cost_usd, latency_ms) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (question, route, answered, top_score, chunk_ids,
             input_tokens, output_tokens, cost_usd, latency_ms),
        )


def answer_question(question: str) -> dict:
    settings = get_settings()
    started = time.monotonic()

    chunks = retrieve(question)
    top_score = chunks[0].similarity if chunks else 0.0

    # Layer 1: if even the best chunk is below the floor, refuse WITHOUT a model
    # call. We still log it (answered=False, no tokens) so nothing is silent.
    if top_score < settings.similarity_floor:
        latency_ms = int((time.monotonic() - started) * 1000)
        _log(question, "refused_low_similarity", False, top_score, [], None, None, 0.0, latency_ms)
        return {
            "answered": False,
            "answer": "That doesn't appear to be discussed in this meeting.",
            "top_score": top_score,
            "citations": [],
        }

    context = "\n\n".join(c.content for c in chunks)
    response = _client_().models.generate_content(
        model=settings.answer_model,
        contents=build_answer_prompt(question, context),
        config=types.GenerateContentConfig(system_instruction=ANSWER_SYSTEM_PROMPT),
    )

    usage = response.usage_metadata
    input_tokens = usage.prompt_token_count
    output_tokens = usage.candidates_token_count
    cost_usd = input_tokens * _INPUT_COST_PER_TOKEN + output_tokens * _OUTPUT_COST_PER_TOKEN
    latency_ms = int((time.monotonic() - started) * 1000)

    _log(question, "answered", True, top_score, [c.chunk_id for c in chunks],
         input_tokens, output_tokens, cost_usd, latency_ms)

    return {
        "answered": True,
        "answer": response.text,
        "top_score": top_score,
        "citations": [
            {
                "chunk_id": c.chunk_id,
                "speakers": c.speakers,
                "ts_start": c.ts_start,
                "ts_end": c.ts_end,
            }
            for c in chunks
        ],
    }
