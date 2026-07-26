from .db import cursor

# Read-only views over query_log. Nothing here writes or aggregates into a new
# table: the log is already the source of truth for every model call, so a
# dashboard that derives from anything else would be able to disagree with it.

_TOTALS = """
SELECT count(*),
       coalesce(sum(cost_usd), 0),
       coalesce(sum(input_tokens), 0),
       coalesce(sum(output_tokens), 0),
       coalesce(round(avg(latency_ms)), 0),
       count(*) FILTER (WHERE error IS NOT NULL)
FROM query_log
"""

_BY_ROUTE = """
SELECT route,
       count(*),
       coalesce(round(avg(latency_ms)), 0),
       coalesce(percentile_disc(0.95) WITHIN GROUP (ORDER BY latency_ms), 0),
       coalesce(sum(cost_usd), 0),
       coalesce(sum(input_tokens), 0),
       coalesce(sum(output_tokens), 0),
       count(*) FILTER (WHERE error IS NOT NULL)
FROM query_log
GROUP BY route
ORDER BY count(*) DESC
"""

# The refusal rate is the guardrail's own scoreboard: it only counts the two
# routes a question can land on, so ingest and extraction calls cannot dilute it.
# Failed attempts are excluded — a quota rejection is not the guardrail refusing.
_GUARDRAIL = """
SELECT count(*) FILTER (WHERE route = 'refused_low_similarity' AND error IS NULL),
       count(*) FILTER (WHERE route IN ('answered', 'refused_low_similarity') AND error IS NULL),
       coalesce(round((avg(top_score) FILTER (WHERE route = 'answered'))::numeric, 3), 0)
FROM query_log
"""

# Grouped so a repeated failure reads as one problem with a count, not as noise.
_FAILURES = """
SELECT route, error, count(*), max(created_at)
FROM query_log
WHERE error IS NOT NULL
GROUP BY route, error
ORDER BY max(created_at) DESC
LIMIT 10
"""

# Which model actually served the traffic. With a fallback chain the preferred
# model is a hope, not a fact — this is where you see the chain being used.
_BY_MODEL = """
SELECT coalesce(model, 'unknown'),
       count(*),
       count(*) FILTER (WHERE error IS NULL),
       count(*) FILTER (WHERE error IS NOT NULL),
       coalesce(sum(cost_usd), 0)
FROM query_log
WHERE model IS NOT NULL
GROUP BY model
ORDER BY count(*) DESC
"""

_BY_MEETING = """
SELECT q.transcript_id,
       coalesce(t.title, t.filename, 'Meeting ' || q.transcript_id),
       count(*),
       count(*) FILTER (WHERE q.route = 'answered'),
       count(*) FILTER (WHERE q.route = 'refused_low_similarity'),
       count(*) FILTER (WHERE q.route = 'extract_actions'),
       coalesce(sum(q.cost_usd), 0),
       coalesce(sum(coalesce(q.input_tokens, 0) + coalesce(q.output_tokens, 0)), 0)
FROM query_log q
LEFT JOIN transcripts t ON t.id = q.transcript_id
WHERE q.transcript_id IS NOT NULL
GROUP BY q.transcript_id, t.title, t.filename
ORDER BY sum(q.cost_usd) DESC
"""

# Surfaced rather than dropped, so the per-meeting rows and the global total
# reconcile. Two honest reasons a call has no meeting: normalize/transcribe run
# before the transcript exists, and older rows predate this column.
_UNATTRIBUTED = """
SELECT count(*), coalesce(sum(cost_usd), 0)
FROM query_log
WHERE transcript_id IS NULL
"""

_RECENT = """
SELECT question, route, answered, top_score, input_tokens, output_tokens,
       cost_usd, latency_ms, created_at, error
FROM query_log
ORDER BY id DESC
LIMIT 25
"""


def get_metrics() -> dict:
    with cursor() as cur:
        cur.execute(_TOTALS)
        calls, cost, input_tokens, output_tokens, avg_latency, failures = cur.fetchone()

        cur.execute(_BY_ROUTE)
        by_route = [
            {
                "route": r[0],
                "calls": r[1],
                "avg_latency_ms": int(r[2]),
                "p95_latency_ms": int(r[3]),
                "cost_usd": float(r[4]),
                "input_tokens": int(r[5]),
                "output_tokens": int(r[6]),
                "failed": r[7],
            }
            for r in cur.fetchall()
        ]

        cur.execute(_FAILURES)
        recent_failures = [
            {"route": r[0], "error": r[1], "count": r[2], "last_seen": r[3].isoformat()}
            for r in cur.fetchall()
        ]

        cur.execute(_GUARDRAIL)
        refused, questions, avg_top_score = cur.fetchone()

        cur.execute(_BY_MODEL)
        by_model = [
            {"model": r[0], "calls": r[1], "ok": r[2], "failed": r[3], "cost_usd": float(r[4])}
            for r in cur.fetchall()
        ]

        cur.execute(_BY_MEETING)
        by_meeting = [
            {
                "transcript_id": r[0],
                "name": r[1],
                "calls": r[2],
                "answered": r[3],
                "refused": r[4],
                "extractions": r[5],
                "cost_usd": float(r[6]),
                "tokens": int(r[7]),
            }
            for r in cur.fetchall()
        ]

        cur.execute(_UNATTRIBUTED)
        unattributed_calls, unattributed_cost = cur.fetchone()

        cur.execute(_RECENT)
        recent = [
            {
                "question": r[0],
                "route": r[1],
                "answered": r[2],
                "top_score": float(r[3]) if r[3] is not None else None,
                "input_tokens": r[4],
                "output_tokens": r[5],
                "cost_usd": float(r[6]) if r[6] is not None else 0.0,
                "latency_ms": r[7],
                "created_at": r[8].isoformat(),
                "error": r[9],
            }
            for r in cur.fetchall()
        ]

    return {
        "totals": {
            "calls": calls,
            "cost_usd": float(cost),
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
            "avg_latency_ms": int(avg_latency),
            "failed": failures,
        },
        "guardrail": {
            "refused": refused,
            "questions": questions,
            # Guarded rather than assumed: the dashboard is often opened before
            # anyone has asked a question.
            "refusal_rate": round(refused / questions, 3) if questions else 0.0,
            "avg_top_score_when_answered": float(avg_top_score),
        },
        "by_route": by_route,
        "by_model": by_model,
        "failures": recent_failures,
        "by_meeting": by_meeting,
        "unattributed": {
            "calls": unattributed_calls,
            "cost_usd": float(unattributed_cost),
        },
        "recent": recent,
    }
