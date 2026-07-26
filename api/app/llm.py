import logging
import time

from google import genai

from .config import get_settings
from .db import cursor

# Approximate gemini flash pricing (USD per token); update if pricing moves.
# Every model call records cost — the CLAUDE.md "no silent model calls" rule.
INPUT_COST_PER_TOKEN = 0.30 / 1_000_000
OUTPUT_COST_PER_TOKEN = 2.50 / 1_000_000

_client: genai.Client | None = None


def client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=get_settings().gemini_api_key)
    return _client


def cost_usd(input_tokens: int | None, output_tokens: int | None) -> float:
    # Token counts can be None (e.g. a call that produced no output), so coerce.
    return (input_tokens or 0) * INPUT_COST_PER_TOKEN + (output_tokens or 0) * OUTPUT_COST_PER_TOKEN


def log_query(
    question: str,
    route: str,
    answered: bool,
    top_score: float | None,
    chunk_ids: list[int],
    input_tokens: int | None,
    output_tokens: int | None,
    cost: float,
    latency_ms: int,
    transcript_id: int | None = None,
    error: str | None = None,
    model: str | None = None,
) -> None:
    with cursor() as cur:
        cur.execute(
            "INSERT INTO query_log (question, route, answered, top_score, chunk_ids, "
            "input_tokens, output_tokens, cost_usd, latency_ms, transcript_id, error, model) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (question, route, answered, top_score, chunk_ids,
             input_tokens, output_tokens, cost, latency_ms, transcript_id, error, model),
        )


def generate_with_fallback(
    question: str,
    route: str,
    started: float,
    transcript_id: int | None = None,
    **kwargs: object,
) -> tuple[object, str]:
    """Try each configured model in order. Returns (response, the model that answered).

    Falls through on *any* failure, not just quota: from the caller's side a model
    that errors and a model that is exhausted are the same event, and the next one
    in the chain is the cheapest thing to try. Each failed attempt is logged as its
    own row, so the dashboard shows the fallback happening rather than hiding it
    behind an eventual success. The last model's error is what finally surfaces.
    """
    last: BaseException | None = None
    for model in get_settings().answer_model_chain:
        try:
            return client().models.generate_content(model=model, **kwargs), model
        except Exception as exc:
            logging.warning("model %s failed (%s), trying next", model, type(exc).__name__)
            log_query(question, route, False, None, [], None, None, 0.0,
                      int((time.monotonic() - started) * 1000), transcript_id,
                      describe_error(exc), model)
            last = exc
    raise last  # type: ignore[misc]


def describe_error(exc: BaseException) -> str:
    # The provider's own message is the useful part (quota limits, model names).
    # Truncated because some carry a full JSON body of retry metadata.
    message = getattr(exc, "message", None) or str(exc)
    code = getattr(exc, "code", None)
    label = f"{code} {type(exc).__name__}" if code else type(exc).__name__
    return f"{label}: {message}"[:400]


def log_failed_call(
    question: str,
    route: str,
    started: float,
    exc: BaseException,
    transcript_id: int | None = None,
) -> None:
    """Record an attempted model call that raised, so it isn't silently lost."""
    log_query(question, route, False, None, [], None, None, 0.0,
              int((time.monotonic() - started) * 1000), transcript_id, describe_error(exc))
