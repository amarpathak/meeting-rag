import hashlib

from .chunking import chunk_turns
from .config import get_settings
from .db import cursor
from .embeddings import embed_documents
from .normalize import normalize_transcript
from .parsing import parse_transcript


def _content_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _to_pgvector(vec: list[float]) -> str:
    # pgvector accepts the literal form '[0.1,0.2,...]'; we cast it with ::vector
    # at insert time rather than pulling in the pgvector Python adapter.
    return "[" + ",".join(str(x) for x in vec) + "]"


def ingest_transcript(filename: str, raw: str) -> dict:
    settings = get_settings()
    content_hash = _content_hash(raw)

    # Idempotency gate — checked BEFORE embedding. The hash needs only the raw
    # bytes, so we spend nothing to discover a re-upload. Embedding is the only
    # step that costs money and network, so it must sit behind this check.
    with cursor() as cur:
        cur.execute("SELECT id FROM transcripts WHERE content_hash = %s", (content_hash,))
        existing = cur.fetchone()
        if existing is not None:
            return {"status": "already_ingested", "transcript_id": existing[0], "chunks": 0}

    parsed = parse_transcript(raw)
    normalized = False
    if not parsed.turns:
        # Not in our [HH:MM:SS] Speaker: text format — try to normalize it with
        # the LLM, then re-parse. If it still yields no turns, it isn't a meeting.
        parsed = parse_transcript(normalize_transcript(raw))
        normalized = True
        if not parsed.turns:
            raise ValueError(
                "Could not read this file as a meeting transcript. Expected "
                "speaker-labelled lines like '[HH:MM:SS] Speaker: text'."
            )

    chunks = chunk_turns(
        parsed.turns, settings.chunk_target_tokens, settings.chunk_overlap_turns
    )
    vectors = embed_documents([c.content for c in chunks])

    # One transaction: transcript row + all chunk rows commit together, so a
    # failure never leaves a transcript with a partial set of chunks. The
    # UNIQUE(content_hash) constraint is the real idempotency guarantee — the
    # pre-check above is the cost optimization; this catches a concurrent race.
    with cursor() as cur:
        cur.execute(
            "INSERT INTO transcripts (filename, title, content_hash) "
            "VALUES (%s, %s, %s) RETURNING id",
            (filename, parsed.title, content_hash),
        )
        transcript_id = cur.fetchone()[0]
        for chunk, vec in zip(chunks, vectors):
            cur.execute(
                "INSERT INTO chunks (transcript_id, chunk_index, content, speakers, "
                "ts_start, ts_end, token_count, embedding) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)",
                (
                    transcript_id,
                    chunk.index,
                    chunk.content,
                    chunk.speakers,
                    chunk.ts_start,
                    chunk.ts_end,
                    chunk.token_count,
                    _to_pgvector(vec),
                ),
            )

    return {
        "status": "ingested",
        "transcript_id": transcript_id,
        "chunks": len(chunks),
        "normalized": normalized,
    }
