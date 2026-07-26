import re
import time
from datetime import datetime

from google.genai import types
from psycopg.types.json import Json
from pydantic import BaseModel

from .config import get_settings
from .db import cursor
from .llm import cost_usd, generate_with_fallback, log_query
from .prompts import ACTIONS_SYSTEM_PROMPT, build_actions_prompt
from .transcripts import transcript_text


class ActionItem(BaseModel):
    owner: str
    task: str
    due: str | None
    timestamp: str


_TIMESTAMP = re.compile(r"(\d{1,2}):([0-5]\d):([0-5]\d)")


def _clean_timestamp(raw: str) -> str:
    # The UI links an action item to its turn by matching this string exactly, so
    # any decoration the model carries over from the transcript's own
    # "[HH:MM:SS] Speaker:" line format silently breaks the link rather than
    # erroring. Pull the digits out instead of trusting the model's formatting.
    match = _TIMESTAMP.search(raw or "")
    if not match:
        return (raw or "").strip()
    hours, minutes, seconds = match.groups()
    return f"{int(hours):02d}:{minutes}:{seconds}"


def _cached(transcript_id: int, models: list[str]) -> tuple[list[dict], datetime] | None:
    # Matches any model still in the configured chain, not just the preferred one:
    # a fallback stores under whichever model actually answered, and keying the
    # read on the preferred model alone would miss it forever and re-extract on
    # every open. Dropping a model from the chain still invalidates its rows.
    with cursor() as cur:
        cur.execute(
            "SELECT items, extracted_at FROM action_items "
            "WHERE transcript_id = %s AND model = ANY(%s)",
            (transcript_id, models),
        )
        row = cur.fetchone()
    return (row[0], row[1]) if row else None


def _store(transcript_id: int, model: str, items: list[dict]) -> datetime:
    # RETURNING rather than a Python clock: the displayed age should come from the
    # same clock as the stored row, not from whichever container rendered it.
    with cursor() as cur:
        cur.execute(
            "INSERT INTO action_items (transcript_id, items, model) VALUES (%s, %s, %s) "
            "ON CONFLICT (transcript_id) DO UPDATE SET items = EXCLUDED.items, "
            "model = EXCLUDED.model, extracted_at = now() "
            "RETURNING extracted_at",
            (transcript_id, Json(items), model),
        )
        return cur.fetchone()[0]


def extract_actions(transcript_id: int, refresh: bool = False) -> dict:
    settings = get_settings()
    started = time.monotonic()

    if not refresh:
        hit = _cached(transcript_id, settings.answer_model_chain)
        if hit is not None:
            items, extracted_at = hit
            return {"transcript_id": transcript_id, "action_items": items,
                    "cached": True, "extracted_at": extracted_at.isoformat()}

    transcript, chunk_ids = transcript_text(transcript_id)
    if not transcript:
        # Nothing to extract from, and nothing worth caching: chunks may still land
        # if this id is mid-ingest.
        return {"transcript_id": transcript_id, "action_items": [], "cached": False,
                "extracted_at": None}

    # Structured output: the model is constrained to JSON matching the ActionItem
    # schema, so we get typed rows instead of prose to parse.
    label = f"extract action items (transcript {transcript_id})"
    response, model = generate_with_fallback(
        label, "extract_actions", started, transcript_id,
        contents=build_actions_prompt(transcript),
        config=types.GenerateContentConfig(
            system_instruction=ACTIONS_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=list[ActionItem],
        ),
    )

    items: list[ActionItem] = response.parsed or []
    usage = response.usage_metadata
    latency_ms = int((time.monotonic() - started) * 1000)
    log_query(
        label,
        "extract_actions",
        True,
        None,
        chunk_ids,
        usage.prompt_token_count,
        usage.candidates_token_count,
        cost_usd(usage.prompt_token_count, usage.candidates_token_count),
        latency_ms,
        transcript_id,
        None,
        model,
    )

    payload = [item.model_dump() for item in items]
    for row in payload:
        row["timestamp"] = _clean_timestamp(row["timestamp"])
    extracted_at = _store(transcript_id, model, payload)

    return {"transcript_id": transcript_id, "action_items": payload, "cached": False,
            "extracted_at": extracted_at.isoformat()}
