"""MCP tool implementations for episode retrieval."""

from __future__ import annotations

from typing import Any

from podcast_mcp.application.episodes import EpisodeService
from podcast_mcp.infrastructure.postgres import PostgresTranscriptRepository


def _service() -> EpisodeService:
    return EpisodeService(PostgresTranscriptRepository())


def list_episodes(limit: int = 25, offset: int = 0) -> list[dict[str, Any]]:
    return [episode.to_dict() for episode in _service().list_episodes(limit, offset)]


def get_episode(episode_id: str | None = None, audio_url: str | None = None) -> dict[str, Any]:
    return _service().get_episode(episode_id, audio_url).to_dict()