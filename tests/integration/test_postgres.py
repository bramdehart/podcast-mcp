"""Integration tests against a real Postgres/pgvector database.

These tests are skipped unless a DATABASE_URL environment variable is set.
Run with a local database:

    DATABASE_URL=postgresql://user:pass@localhost:5432/podcast_mcp pytest tests/integration
"""

from __future__ import annotations

import os

import pytest

from podcast_mcp.infrastructure.postgres import PostgresTranscriptRepository

_DATABASE_URL = os.getenv("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not _DATABASE_URL or "<" in _DATABASE_URL,
    reason="DATABASE_URL not set to a reachable database",
)


@pytest.fixture
def repository() -> PostgresTranscriptRepository:
    return PostgresTranscriptRepository()


def test_list_episodes_returns_rows(repository: PostgresTranscriptRepository) -> None:
    episodes = repository.list_episodes(limit=10, offset=0)
    assert isinstance(episodes, list)


def test_get_missing_episode_raises(repository: PostgresTranscriptRepository) -> None:
    with pytest.raises(LookupError):
        repository.get_episode(episode_id="00000000-0000-0000-0000-000000000000")


def test_around_timestamp_missing_episode_raises(repository: PostgresTranscriptRepository) -> None:
    with pytest.raises(LookupError):
        repository.get_transcript_around_timestamp(
            "00000000-0000-0000-0000-000000000000",
            timestamp_seconds=0.0,
            context_seconds=60,
        )


def test_search_by_speaker_requires_filter(repository: PostgresTranscriptRepository) -> None:
    with pytest.raises(ValueError):
        repository.search_by_speaker(
            speaker_name=None,
            speaker_id=None,
            query_embedding=None,
            episode_id=None,
            limit=5,
        )