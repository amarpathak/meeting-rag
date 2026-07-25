import time

from google.genai import types

from .config import get_settings
from .llm import client, cost_usd, log_query
from .prompts import ANSWER_SYSTEM_PROMPT, build_answer_prompt
from .retrieval import retrieve


def answer_question(question: str) -> dict:
    settings = get_settings()
    started = time.monotonic()

    chunks = retrieve(question)
    top_score = chunks[0].similarity if chunks else 0.0

    # Layer 1: if even the best chunk is below the floor, refuse WITHOUT a model
    # call. Still logged (answered=False, no tokens) so nothing is silent.
    if top_score < settings.similarity_floor:
        latency_ms = int((time.monotonic() - started) * 1000)
        log_query(question, "refused_low_similarity", False, top_score, [], None, None, 0.0, latency_ms)
        return {
            "answered": False,
            "answer": "That doesn't appear to be discussed in this meeting.",
            "top_score": top_score,
            "citations": [],
        }

    context = "\n\n".join(c.content for c in chunks)
    response = client().models.generate_content(
        model=settings.answer_model,
        contents=build_answer_prompt(question, context),
        config=types.GenerateContentConfig(system_instruction=ANSWER_SYSTEM_PROMPT),
    )

    usage = response.usage_metadata
    input_tokens = usage.prompt_token_count
    output_tokens = usage.candidates_token_count
    latency_ms = int((time.monotonic() - started) * 1000)

    log_query(question, "answered", True, top_score, [c.chunk_id for c in chunks],
              input_tokens, output_tokens, cost_usd(input_tokens, output_tokens), latency_ms)

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
