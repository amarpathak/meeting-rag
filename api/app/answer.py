import time
from datetime import datetime

from google.genai import types
from psycopg.types.json import Json

from .config import get_settings
from .db import cursor
from .llm import cost_usd, generate_with_fallback, log_query
from .prompts import ANSWER_SYSTEM_PROMPT, build_answer_prompt
from .retrieval import retrieve


def _cache_key(question: str) -> str:
    # Whitespace and capitalisation are not part of what was asked. Without this,
    # clicking a recent chip would hit but retyping the same question by hand would
    # miss, and two questions that are the same question would cost different money.
    return " ".join(question.split()).casefold()


def _cached(transcript_id: int, question: str, models: list[str]) -> tuple[dict, datetime] | None:
    # Matches any model still in the configured chain rather than the preferred one
    # only, for the same reason as the action-item cache: a fallback stores under
    # whichever model actually answered.
    with cursor() as cur:
        cur.execute(
            "SELECT response, answered_at FROM answer_cache "
            "WHERE transcript_id = %s AND question = %s AND model = ANY(%s) LIMIT 1",
            (transcript_id, _cache_key(question), models),
        )
        row = cur.fetchone()
    return (row[0], row[1]) if row else None


def _store(transcript_id: int, question: str, model: str, response: dict) -> datetime:
    with cursor() as cur:
        cur.execute(
            "INSERT INTO answer_cache (transcript_id, question, model, response) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (transcript_id, question, model) DO UPDATE SET "
            "response = EXCLUDED.response, answered_at = now() "
            "RETURNING answered_at",
            (transcript_id, _cache_key(question), model, Json(response)),
        )
        return cur.fetchone()[0]


def answer_question(question: str, transcript_id: int | None = None, refresh: bool = False) -> dict:
    settings = get_settings()
    started = time.monotonic()

    # Only scoped questions are cached. An unscoped question searches every meeting,
    # so its answer changes as meetings are ingested and it is not a pure function
    # of anything we can key on.
    cacheable = transcript_id is not None
    if cacheable and not refresh:
        hit = _cached(transcript_id, question, settings.answer_model_chain)
        if hit is not None:
            response, answered_at = hit
            return {**response, "cached": True, "answered_at": answered_at.isoformat()}

    chunks = retrieve(question, transcript_id)
    top_score = chunks[0].similarity if chunks else 0.0

    # Layer 1: if even the best chunk is below the floor, refuse WITHOUT a model
    # call. Still logged (answered=False, no tokens) so nothing is silent.
    #
    # Deliberately not cached: a refusal already costs no model call, so caching it
    # would save one embedding and in exchange hide every refusal from the guardrail
    # metrics, which are the one place the floor's behaviour is visible.
    if top_score < settings.similarity_floor:
        latency_ms = int((time.monotonic() - started) * 1000)
        log_query(question, "refused_low_similarity", False, top_score, [], None, None, 0.0,
                  latency_ms, transcript_id)
        return {
            "answered": False,
            "answer": "That doesn't appear to be discussed in this meeting.",
            "top_score": top_score,
            "citations": [],
            "cached": False,
            "answered_at": None,
        }

    context = "\n\n".join(c.content for c in chunks)
    response, model = generate_with_fallback(
        question, "answered", started, transcript_id,
        contents=build_answer_prompt(question, context),
        config=types.GenerateContentConfig(system_instruction=ANSWER_SYSTEM_PROMPT),
    )

    usage = response.usage_metadata
    input_tokens = usage.prompt_token_count
    output_tokens = usage.candidates_token_count
    latency_ms = int((time.monotonic() - started) * 1000)

    log_query(question, "answered", True, top_score, [c.chunk_id for c in chunks],
              input_tokens, output_tokens, cost_usd(input_tokens, output_tokens), latency_ms,
              transcript_id, None, model)

    payload = {
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

    answered_at = _store(transcript_id, question, model, payload) if cacheable else None
    return {**payload, "cached": False,
            "answered_at": answered_at.isoformat() if answered_at else None}
