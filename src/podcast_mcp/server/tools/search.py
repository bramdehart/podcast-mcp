"""MCP tool implementations for semantic transcript search."""

from __future__ import annotations

from typing import Any

from podcast_mcp.application.search import TranscriptSearch
from podcast_mcp.infrastructure.embeddings import OpenAIEmbeddingClient
from podcast_mcp.infrastructure.postgres import PostgresTranscriptRepository

DEFAULT_SEARCH_LIMIT = 5
DEFAULT_AROUND_CONTEXT_SECONDS = 60


def _service() -> TranscriptSearch:
    return TranscriptSearch(PostgresTranscriptRepository(), OpenAIEmbeddingClient())


def search_podcast_transcripts(
    query: str,
    limit: int = DEFAULT_SEARCH_LIMIT,
    episode_id: str | None = None,
) -> list[dict[str, Any]]:
    chunks = _service().search(query, limit, episode_id)
    return [chunk.to_dict() for chunk in chunks]


def get_transcript_around_timestamp(
    episode_id: str,
    timestamp_seconds: float,
    context_seconds: int = DEFAULT_AROUND_CONTEXT_SECONDS,
) -> dict[str, Any]:
    return _service().around_timestamp(episode_id, timestamp_seconds, context_seconds).to_dict()