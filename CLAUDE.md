# Working conventions

Read this before generating code in this repo.

## What this is

A meeting intelligence system: ingest transcripts with speaker labels and
timestamps, answer questions about them with grounded citations, and extract
action items.

## Boundaries — where AI assistance is and isn't used

Hand-written, reviewed line by line:
- chunking strategy (`app/chunking.py`)
- retrieval and the similarity floor (`app/retrieval.py`)
- all prompts (`app/prompts.py`)
- the eval harness and its question set

Generated then reviewed:
- Dockerfiles, compose, boilerplate wiring
- frontend components and styling
- test scaffolding

Rationale: the retrieval and prompt layers are where the engineering judgment
lives and where failures are silent. Boilerplate failures are loud, so
generating it is cheap.

## Rules

- Python 3.12, type hints on every function signature.
- No orchestration framework unless the flow actually branches. A single
  retrieve-then-generate path is a function, not a graph.
- Prompts live in `app/prompts.py` as named constants, never inline in logic.
- Comments explain *why*, not *what*. Delete any comment that restates the code.
- No new dependency without a one-line justification beside it in
  `requirements.txt`.
- Never propose a threshold without a measurement behind it. `SIMILARITY_FLOOR`
  came out of the floor sweep in `evals/`; anything else should too.

## Model calls

- Every call records input tokens, output tokens, cost, latency and the model
  that served it into `query_log`. No silent model calls.
- Failed calls are logged too, with the provider's own message. Logging only
  successes makes the dashboard look healthiest exactly when quota has run out.
- Never let the model answer from weak context. If top similarity is below
  `SIMILARITY_FLOOR`, refuse without calling the LLM.
- Generation goes through the fallback chain in `llm.generate_with_fallback`,
  never a bare client call. Free-tier quota is per project *per model*.
- Pin model versions. `-latest` aliases move under you, which changes the quota
  bucket and makes eval numbers either side of the shift incomparable.
- Upstream failures keep their own status codes: 429 quota, 503 unreachable,
  504 timeout. An opaque 500 sends the reader hunting for a bug in this codebase.
- Never let the model's formatting be load-bearing. If something joins on model
  output, normalise it in code first. A prompt asking for `the [HH:MM:SS]` once
  returned `"[00:02:30]"` and silently broke every citation link.

## Caching

Anything that is a pure function of an immutable transcript gets cached, keyed on
the model that produced it, with no TTL. That covers action items and answers.
Do not cache refusals: they cost no model call, and caching them would hide every
refusal from the guardrail metrics.

## Schema

`db/init.sql` only runs on an empty volume. A schema change has to be applied by
hand to the running database *and* added to the file, and both need verifying
against a fresh `docker compose down -v`. This is known debt; a migration tool is
the real fix.

## Testing

pytest, targeting what would fail silently rather than a coverage number: chunker
boundaries, the similarity floor triggering a refusal, ingest idempotency, cache
hit and miss, timestamp normalisation, upstream error mapping, and the
sample-name path guard.

Eval data lives in `data/transcripts/`. An eval set must not depend on anything
fetched at run time, or a fresh clone quietly runs half the suite.

## UI

Say what an action costs before it is taken: the load dialog labels each entry
point with its model-call cost. Never report a failure as an empty result. A
failed extraction showing "No action items found" is worse than an error.

## Commit style

Small, frequent, imperative mood. `add chunker`, not `added chunking stuff`. The
body says why, not what. If a change is too big to review in one diff, it was too
big to ask for.
