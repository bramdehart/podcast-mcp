"""Application service for speaker-based transcript lookup."""

from __future__ import annotations

from podcast_mcp.domain.transcript import TranscriptChunk
from podcast_mcp.infrastructure.embeddings import EmbeddingClient
from podcast_mcp.infrastructure.postgres import TranscriptRepository


class SpeakerService:
    """Search or list transcript chunks attributed to a speaker."""

    def __init__(self, repository: TranscriptRepository, embeddings: EmbeddingClient) -> None:
        self.repository = repository
        self.embeddings = embeddings

    def search(
        self,
        speaker_name: str | None = None,
        speaker_id: str | None = None,
        query: str | None = None,
        episode_id: str | None = None,
        limit: int = 5,
    ) -> list[TranscriptChunk]:
        query_embedding = self.embeddings.embed([query])[0] if query else None
        return self.repository.search_by_speaker(
            speaker_name,
            speaker_id,
            query_embedding,
            episode_id,
            limit,
        )