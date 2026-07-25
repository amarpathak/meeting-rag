from .db import cursor
from .parsing import parse_transcript


def transcript_text(transcript_id: int) -> tuple[str, list[int]]:
    # Rebuild a transcript from its stored chunks. Chunks overlap by one turn, so
    # dedupe identical lines (timestamps make each turn line unique).
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


def list_transcripts() -> list[dict]:
    with cursor() as cur:
        cur.execute(
            "SELECT t.id, t.title, t.filename, t.uploaded_at, count(c.id) "
            "FROM transcripts t LEFT JOIN chunks c ON c.transcript_id = t.id "
            "GROUP BY t.id ORDER BY t.id"
        )
        rows = cur.fetchall()
    return [
        {
            "id": r[0],
            "title": r[1],
            "filename": r[2],
            "uploaded_at": r[3].isoformat() if r[3] else None,
            "chunks": r[4],
        }
        for r in rows
    ]


def get_transcript(transcript_id: int) -> dict:
    with cursor() as cur:
        cur.execute("SELECT title FROM transcripts WHERE id = %s", (transcript_id,))
        row = cur.fetchone()
    if row is None:
        return {"id": transcript_id, "title": None, "turns": []}

    text, _ = transcript_text(transcript_id)
    turns = parse_transcript(text).turns
    return {
        "id": transcript_id,
        "title": row[0],
        "turns": [
            {"timestamp": t.timestamp, "speaker": t.speaker, "text": t.text}
            for t in turns
        ],
    }
