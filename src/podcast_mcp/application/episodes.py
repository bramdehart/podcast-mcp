"""Application service for episode retrieval."""

from __future__ import annotations

from podcast_mcp.domain.episode import Episode
from podcast_mcp.infrastructure.postgres import TranscriptRepository


class EpisodeService:
    """High-level operations over indexed podcast episodes."""

    def __init__(self, repository: TranscriptRepository) -> None:
        self.repository = repository

    def list_episodes(self, limit: int = 25, offset: int = 0) -> list[Episode]:
        return self.repository.list_episodes(limit, offset)

    def get_episode(self, episode_id: str | None = None, audio_url: str | None = None) -> Episode:
        return self.repository.get_episode(episode_id, audio_url)