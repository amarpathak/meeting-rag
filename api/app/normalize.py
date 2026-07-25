import time

from google.genai import types

from .config import get_settings
from .llm import client, cost_usd, log_query
from .prompts import NORMALIZE_SYSTEM_PROMPT, build_normalize_prompt


def normalize_transcript(raw: str) -> str:
    # Reformat arbitrary meeting text into our [HH:MM:SS] Speaker: text format.
    # Used only as a fallback when structured parsing finds no turns.
    settings = get_settings()
    started = time.monotonic()
    response = client().models.generate_content(
        model=settings.answer_model,
        contents=build_normalize_prompt(raw),
        config=types.GenerateContentConfig(system_instruction=NORMALIZE_SYSTEM_PROMPT),
    )
    usage = response.usage_metadata
    log_query(
        "normalize uploaded transcript",
        "normalize",
        True,
        None,
        [],
        usage.prompt_token_count,
        usage.candidates_token_count,
        cost_usd(usage.prompt_token_count, usage.candidates_token_count),
        int((time.monotonic() - started) * 1000),
    )
    return response.text or ""
