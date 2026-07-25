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


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    return input_tokens * INPUT_COST_PER_TOKEN + output_tokens * OUTPUT_COST_PER_TOKEN


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
) -> None:
    with cursor() as cur:
        cur.execute(
            "INSERT INTO query_log (question, route, answered, top_score, chunk_ids, "
            "input_tokens, output_tokens, cost_usd, latency_ms) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (question, route, answered, top_score, chunk_ids,
             input_tokens, output_tokens, cost, latency_ms),
        )
