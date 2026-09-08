"""Application service for semantic transcript search."""

from __future__ import annotations

from podcast_mcp.domain.transcript import TranscriptChunk, TranscriptContext
from podcast_mcp.infrastructure.embeddings import EmbeddingClient
from podcast_mcp.infrastructure.postgres import TranscriptRepository


class TranscriptSearch:
    """Semantic search over transcript chunks backed by an embedding client."""

    def __init__(self, repository: TranscriptRepository, embeddings: EmbeddingClient) -> None:
        self.repository = repository
        self.embeddings = embeddings

    def search(
        self,
        query: str,
        limit: int = 5,
        episode_id: str | None = None,
    ) -> list[TranscriptChunk]:
        embedding = self.embeddings.embed([query])[0]
        return self.repository.search_transcripts(embedding, limit, episode_id)

    def around_timestamp(
        self,
        episode_id: str,
        timestamp_seconds: float,
        context_seconds: int = 60,
    ) -> TranscriptContext:
        return self.repository.get_transcript_around_timestamp(episode_id, timestamp_seconds, context_seconds)