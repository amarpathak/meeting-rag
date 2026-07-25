from dataclasses import dataclass

from .config import get_settings
from .db import cursor
from .embeddings import embed_query


@dataclass(frozen=True)
class Retrieved:
    chunk_id: int
    content: str
    speakers: list[str]
    ts_start: str
    ts_end: str
    similarity: float


def _to_pgvector(vec: list[float]) -> str:
    return "[" + ",".join(str(x) for x in vec) + "]"


def retrieve(question: str) -> list[Retrieved]:
    settings = get_settings()
    q_literal = _to_pgvector(embed_query(question))

    # `embedding <=> query` is cosine DISTANCE (0 = same direction). We report
    # `1 - distance` as similarity (1 = same direction) and sort by it, so the
    # closest chunks come first. At this scale a sequential scan is fine; with
    # many transcripts you'd `ORDER BY embedding <=> query` to use the index.
    with cursor() as cur:
        cur.execute(
            "SELECT id, content, speakers, ts_start, ts_end, "
            "       1 - (embedding <=> %s::vector) AS similarity "
            "FROM chunks "
            "ORDER BY similarity DESC "
            "LIMIT %s",
            (q_literal, settings.top_k),
        )
        rows = cur.fetchall()

    return [
        Retrieved(
            chunk_id=r[0],
            content=r[1],
            speakers=r[2],
            ts_start=r[3],
            ts_end=r[4],
            similarity=float(r[5]),
        )
        for r in rows
    ]
