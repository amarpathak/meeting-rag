import logging

import httpx
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from google.genai import errors as genai_errors
from pydantic import BaseModel

from . import db
from .actions import extract_actions
from .answer import answer_question
from .config import get_settings
from .ingest import ingest_transcript
from .normalize import normalize_transcript
from .observability import get_metrics
from .samples import ingest_all_samples, ingest_sample, list_samples
from .youtube import YouTubeError, fetch_youtube_captions, video_id
from .transcription import transcribe_audio
from .transcripts import get_transcript, list_transcripts

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)

app = FastAPI(title="Meeting Intelligence", version="0.1.0")


@app.exception_handler(genai_errors.APIError)
def genai_error(request: Request, exc: genai_errors.APIError) -> JSONResponse:
    # A quota or auth failure upstream is actionable by whoever is running this;
    # collapsing it into an opaque 500 hides the one detail that explains the fix.
    code = getattr(exc, "code", None)
    status = code if isinstance(code, int) and 400 <= code < 600 else 502
    logging.error("gemini api error %s: %s", code, exc.message)
    return JSONResponse(status_code=status, content={"detail": f"Gemini API error: {exc.message}"})


@app.exception_handler(httpx.RequestError)
def upstream_unreachable(request: Request, exc: httpx.RequestError) -> JSONResponse:
    # The request never reached Gemini — offline, DNS down, or a timeout. This is
    # not the same failure as a rejected request, and saying so saves the reader
    # from checking their quota when the real problem is their network.
    timeout = isinstance(exc, httpx.TimeoutException)
    detail = (
        "Timed out reaching the Gemini API. Check your network connection and retry."
        if timeout
        else f"Cannot reach the Gemini API — check your network connection. ({exc})"
    )
    logging.error("gemini unreachable: %r", exc)
    return JSONResponse(status_code=504 if timeout else 503, content={"detail": detail})


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
        "answer_model_chain": settings.answer_model_chain,
        "keys_present": {
            "gemini": bool(settings.gemini_api_key),
        },
    }


@app.post("/ingest")
async def ingest(file: UploadFile) -> dict:
    try:
        raw = (await file.read()).decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 text.")
    try:
        return ingest_transcript(file.filename or "upload.txt", raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/samples")
def samples() -> list[dict]:
    return list_samples()


@app.post("/ingest-sample")
def load_sample(name: str | None = None) -> dict:
    # Bundled transcripts, offered one at a time so someone can load the meeting
    # they want rather than all of them. No name still means all of them, which is
    # what the "load the samples" path in the README does.
    try:
        results = [ingest_sample(name)] if name else ingest_all_samples()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ingested": results}


@app.get("/transcripts")
def transcripts() -> list[dict]:
    return list_transcripts()


@app.get("/transcripts/{transcript_id}")
def transcript(transcript_id: int) -> dict:
    return get_transcript(transcript_id)


class AskRequest(BaseModel):
    question: str
    transcript_id: int | None = None
    refresh: bool = False


@app.post("/ask")
def ask(req: AskRequest) -> dict:
    return answer_question(req.question, req.transcript_id, req.refresh)


class YouTubeRequest(BaseModel):
    url: str


@app.post("/ingest-youtube")
def ingest_youtube(req: YouTubeRequest) -> dict:
    try:
        title, captions, truncated = fetch_youtube_captions(req.url)
    except YouTubeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Captions carry timestamps but no speakers, so they go through the same
    # normaliser used for odd uploads — it infers the turn boundaries and labels.
    # Diarization is therefore best-effort, exactly as with the audio path.
    body = normalize_transcript(captions)
    raw = f"Meeting: {title}\n\n{body}"
    try:
        result = ingest_transcript(f"youtube-{video_id(req.url)}.txt", raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {**result, "title": title, "truncated": truncated}


@app.get("/observability")
def observability() -> dict:
    return get_metrics()


@app.get("/transcripts/{transcript_id}/actions")
def actions(transcript_id: int, refresh: bool = False) -> dict:
    return extract_actions(transcript_id, refresh)


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
        try:
            result["ingest"] = ingest_transcript(file.filename or "audio.txt", result["transcript"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    return result
