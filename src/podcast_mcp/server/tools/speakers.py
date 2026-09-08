"""MCP tool implementations for speaker-based transcript lookup."""

from __future__ import annotations

from typing import Any

from podcast_mcp.application.speakers import SpeakerService
from podcast_mcp.infrastructure.embeddings import OpenAIEmbeddingClient
from podcast_mcp.infrastructure.postgres import PostgresTranscriptRepository

DEFAULT_SEARCH_LIMIT = 5


def _service() -> SpeakerService:
    return SpeakerService(PostgresTranscriptRepository(), OpenAIEmbeddingClient())


def search_by_speaker(
    speaker_name: str | None = None,
    speaker_id: str | None = None,
    query: str | None = None,
    episode_id: str | None = None,
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> list[dict[str, Any]]:
    chunks = _service().search(speaker_name, speaker_id, query, episode_id, limit)
    return [chunk.to_dict() for chunk in chunks]