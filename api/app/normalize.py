import time

from google.genai import types

from .config import get_settings
from .llm import cost_usd, generate_with_fallback, log_query
from .prompts import NORMALIZE_SYSTEM_PROMPT, build_normalize_prompt


def normalize_transcript(raw: str) -> str:
    # Reformat arbitrary meeting text into our [HH:MM:SS] Speaker: text format.
    # Used only as a fallback when structured parsing finds no turns.
    started = time.monotonic()
    response, model = generate_with_fallback(
        "normalize uploaded transcript", "normalize", started, None,
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
        None,
        None,
        model,
    )
    return response.text or ""
