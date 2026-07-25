import time

from google.genai import types

from .config import get_settings
from .llm import client, cost_usd, log_query
from .prompts import TRANSCRIBE_INSTRUCTION, TRANSCRIBE_SYSTEM_PROMPT


def transcribe_audio(filename: str, audio: bytes, mime_type: str) -> dict:
    settings = get_settings()
    started = time.monotonic()

    # Gemini is multimodal: pass the audio bytes as a content Part alongside the
    # text instruction. The prompt forces output into our [ts] Speaker: text
    # format, so the transcript drops straight into the existing parser.
    response = client().models.generate_content(
        model=settings.answer_model,
        contents=[
            types.Part.from_bytes(data=audio, mime_type=mime_type),
            TRANSCRIBE_INSTRUCTION,
        ],
        config=types.GenerateContentConfig(system_instruction=TRANSCRIBE_SYSTEM_PROMPT),
    )

    usage = response.usage_metadata
    latency_ms = int((time.monotonic() - started) * 1000)
    log_query(
        f"transcribe audio ({filename})",
        "transcribe",
        True,
        None,
        [],
        usage.prompt_token_count,
        usage.candidates_token_count,
        cost_usd(usage.prompt_token_count, usage.candidates_token_count),
        latency_ms,
    )
    return {"filename": filename, "transcript": response.text}
