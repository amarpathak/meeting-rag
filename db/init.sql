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
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
