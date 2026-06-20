CREATE TABLE IF NOT EXISTS episode_speakers (
    episode_id uuid NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    speaker_id text NOT NULL,
    speaker_name text,
    speaker_confidence numeric(5, 4),
    evidence text,
    PRIMARY KEY (episode_id, speaker_id),
    CHECK (speaker_confidence IS NULL OR (speaker_confidence >= 0 AND speaker_confidence <= 1))
);

CREATE TABLE IF NOT EXISTS transcript_segments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    episode_id uuid NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    text text NOT NULL,
    start_seconds numeric(10, 3) NOT NULL,
    end_seconds numeric(10, 3) NOT NULL,
    speaker_id text,
    speaker_name text,
    speaker_confidence numeric(5, 4),
    diarization_confidence numeric(5, 4),
    CHECK (end_seconds >= start_seconds),
    CHECK (speaker_confidence IS NULL OR (speaker_confidence >= 0 AND speaker_confidence <= 1)),
    CHECK (diarization_confidence IS NULL OR (diarization_confidence >= 0 AND diarization_confidence <= 1))
);

CREATE INDEX IF NOT EXISTS idx_episode_speakers_episode_id
    ON episode_speakers (episode_id);

CREATE INDEX IF NOT EXISTS idx_transcript_segments_episode_id
    ON transcript_segments (episode_id);

CREATE INDEX IF NOT EXISTS idx_transcript_segments_speaker
    ON transcript_segments (episode_id, speaker_id);

ALTER TABLE transcript_chunks
    ADD COLUMN IF NOT EXISTS speaker_id text,
    ADD COLUMN IF NOT EXISTS speaker_name text,
    ADD COLUMN IF NOT EXISTS speaker_confidence numeric(5, 4);
