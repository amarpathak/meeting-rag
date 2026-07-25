import logging

from fastapi import FastAPI, UploadFile
from pydantic import BaseModel

from . import db
from .actions import extract_actions
from .answer import answer_question
from .config import get_settings
from .ingest import ingest_transcript
from .transcription import transcribe_audio

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
            "gemini": bool(settings.gemini_api_key),
        },
    }


@app.post("/ingest")
async def ingest(file: UploadFile) -> dict:
    raw = (await file.read()).decode("utf-8")
    return ingest_transcript(file.filename or "upload.txt", raw)


class AskRequest(BaseModel):
    question: str


@app.post("/ask")
def ask(req: AskRequest) -> dict:
    return answer_question(req.question)


@app.get("/transcripts/{transcript_id}/actions")
def actions(transcript_id: int) -> dict:
    return extract_actions(transcript_id)


_AUDIO_MIME = {
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".aiff": "audio/aiff",
    ".aif": "audio/aiff", ".m4a": "audio/mp4", ".flac": "audio/flac",
    ".ogg": "audio/ogg", ".aac": "audio/aac",
}


def _audio_mime(file: UploadFile) -> str:
    content_type = (file.content_type or "").lower()
    if content_type.startswith("audio/"):
        return content_type
    name = (file.filename or "").lower()
    for ext, mime in _AUDIO_MIME.items():
        if name.endswith(ext):
            return mime
    return "audio/mpeg"


@app.post("/transcribe")
async def transcribe(file: UploadFile, ingest: bool = False) -> dict:
    audio = await file.read()
    result = transcribe_audio(file.filename or "audio", audio, _audio_mime(file))
    if ingest:
        result["ingest"] = ingest_transcript(file.filename or "audio.txt", result["transcript"])
    return result
