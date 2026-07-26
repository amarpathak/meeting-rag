CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS transcripts (
    id           BIGSERIAL PRIMARY KEY,
    filename     TEXT NOT NULL,
    title        TEXT,
    content_hash TEXT NOT NULL UNIQUE,
    uploaded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- content_hash makes ingestion idempotent: re-uploading the same file is a no-op
-- rather than silently doubling every chunk in the index.

CREATE TABLE IF NOT EXISTS chunks (
    id            BIGSERIAL PRIMARY KEY,
    transcript_id BIGINT NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    chunk_index   INT NOT NULL,
    content       TEXT NOT NULL,
    speakers      TEXT[] NOT NULL DEFAULT '{}',
    ts_start      TEXT,
    ts_end        TEXT,
    token_count   INT,
    embedding     VECTOR(768),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (transcript_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS chunks_transcript_idx ON chunks (transcript_id);

-- IVFFlat needs training data to be useful, so it is created but will only
-- start helping once there are enough rows. At assignment scale a sequential
-- scan is faster; the index is here to show the production intent.
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Action items are a pure function of a transcript, and transcripts are immutable
-- (content_hash is unique, ingest is idempotent), so the extraction is cacheable
-- indefinitely. Without this, every meeting switch in the UI burned an LLM call.
-- model is part of the key, not just metadata: the fallback chain means an
-- extraction may be served by whichever model was reachable at the time, so rows
-- produced by one model must not later be served as another's.
CREATE TABLE IF NOT EXISTS action_items (
    transcript_id BIGINT PRIMARY KEY REFERENCES transcripts(id) ON DELETE CASCADE,
    items         JSONB NOT NULL,
    model         TEXT NOT NULL,
    extracted_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Same purity argument as action_items: an answer is a function of (transcript,
-- question, model) and transcripts are immutable, so an identical question asked
-- twice does not need a second model call. This is not a speculative optimisation
-- — the UI hands out two affordances that replay a question verbatim (the recent
-- chips and the six starter buttons), so exact repeats are the common case, not
-- the rare one. The question is stored whitespace-collapsed and casefolded, since
-- neither is part of what was asked.
CREATE TABLE IF NOT EXISTS answer_cache (
    transcript_id BIGINT NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    question      TEXT NOT NULL,
    model         TEXT NOT NULL,
    response      JSONB NOT NULL,
    answered_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (transcript_id, question, model)
);

CREATE TABLE IF NOT EXISTS query_log (
    id            BIGSERIAL PRIMARY KEY,
    question      TEXT NOT NULL,
    route         TEXT,
    answered      BOOLEAN NOT NULL,
    top_score     REAL,
    chunk_ids     BIGINT[],
    input_tokens  INT,
    output_tokens INT,
    cost_usd      NUMERIC(10, 6),
    latency_ms    INT,
    -- Recorded explicitly rather than derived from chunk_ids: a refusal makes no
    -- model call and cites no chunks, but it is still a cost attributable to the
    -- meeting that was asked about. NULL for normalize/transcribe, which run
    -- before a transcript row exists. SET NULL on delete so removing a meeting
    -- does not erase spend that was genuinely incurred.
    transcript_id BIGINT REFERENCES transcripts(id) ON DELETE SET NULL,
    -- A call that was rejected (quota) or never arrived (offline) is still a call
    -- we attempted. Logging only successes made failures invisible in the
    -- dashboard, which is exactly when you most want to look at it.
    error         TEXT,
    -- Which model actually served this call. With a fallback chain the answer may
    -- not come from the preferred model, and "which model produced this" is not
    -- recoverable after the fact.
    model         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS query_log_transcript_idx ON query_log (transcript_id);
