import time

from google.genai import types
from pydantic import BaseModel

from .config import get_settings
from .db import cursor
from .llm import client, cost_usd, log_query
from .prompts import ACTIONS_SYSTEM_PROMPT, build_actions_prompt


class ActionItem(BaseModel):
    owner: str
    task: str
    due: str | None
    timestamp: str


def _transcript_text(transcript_id: int) -> tuple[str, list[int]]:
    # Rebuild the transcript from its stored chunks. Chunks overlap by one turn,
    # so we dedupe identical lines (timestamps are unique) to get each turn once.
    with cursor() as cur:
        cur.execute(
            "SELECT id, content FROM chunks WHERE transcript_id = %s ORDER BY chunk_index",
            (transcript_id,),
        )
        rows = cur.fetchall()

    chunk_ids = [r[0] for r in rows]
    seen: set[str] = set()
    lines: list[str] = []
    for _, content in rows:
        for line in content.split("\n"):
            if line and line not in seen:
                seen.add(line)
                lines.append(line)
    return "\n".join(lines), chunk_ids


def extract_actions(transcript_id: int) -> dict:
    settings = get_settings()
    started = time.monotonic()

    transcript, chunk_ids = _transcript_text(transcript_id)
    if not transcript:
        return {"transcript_id": transcript_id, "action_items": []}

    # Structured output: the model is constrained to return JSON matching the
    # ActionItem schema, so we get typed rows instead of prose to parse.
    response = client().models.generate_content(
        model=settings.answer_model,
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
        f"extract action items (transcript {transcript_id})",
        "extract_actions",
        True,
        None,
        chunk_ids,
        usage.prompt_token_count,
        usage.candidates_token_count,
        cost_usd(usage.prompt_token_count, usage.candidates_token_count),
        latency_ms,
    )

    return {
        "transcript_id": transcript_id,
        "action_items": [item.model_dump() for item in items],
    }
