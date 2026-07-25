import logging

from fastapi import FastAPI

from . import db
from .config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)

app = FastAPI(title="Meeting Intelligence", version="0.1.0")


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    try:
        db_ok = db.ping()
        vector_ok = db.vector_extension_ready()
    except Exception as exc:  # surfaced deliberately: health should explain itself
        return {"status": "degraded", "db": False, "pgvector": False, "error": str(exc)}

    return {
        "status": "ok" if db_ok and vector_ok else "degraded",
        "db": db_ok,
        "pgvector": vector_ok,
        "embedding_model": settings.embedding_model,
        "answer_model": settings.answer_model,
        "keys_present": {
            "anthropic": bool(settings.anthropic_api_key),
            "openai": bool(settings.openai_api_key),
        },
    }
