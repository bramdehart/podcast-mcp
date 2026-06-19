CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS episodes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    titel text NOT NULL,
    datum timestamptz,
    audio_url text NOT NULL UNIQUE,
    duur integer
);

CREATE TABLE IF NOT EXISTS transcript_chunks (
    episode_id uuid NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    text text NOT NULL,
    start_seconds numeric(10, 3) NOT NULL,
    end_seconds numeric(10, 3) NOT NULL,
    embedding vector(1536) NOT NULL,
    CHECK (end_seconds >= start_seconds)
);

CREATE INDEX IF NOT EXISTS idx_transcript_chunks_episode_id
    ON transcript_chunks (episode_id);

CREATE INDEX IF NOT EXISTS idx_transcript_chunks_embedding
    ON transcript_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
