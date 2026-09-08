"""Postgres repository implementing the transcript repository interface."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

import psycopg

from podcast_mcp.config import settings
from podcast_mcp.domain.episode import Episode
from podcast_mcp.domain.speaker import Speaker
from podcast_mcp.domain.transcript import TranscriptChunk, TranscriptContext, TranscriptSegment
from podcast_mcp.infrastructure.embeddings import vector_literal


def database_url() -> str:
    return settings.require_database_url()


@contextmanager
def _cursor() -> Iterator[psycopg.Cursor[Any]]:
    with psycopg.connect(
        database_url(),
        row_factory=psycopg.rows.dict_row,
    ) as connection, connection.cursor() as cursor:
        yield cursor


def json_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def row_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {key: json_value(value) for key, value in row.items()}


class TranscriptRepository(Protocol):
    """Read-only interface for transcript and episode data."""

    def list_episodes(self, limit: int, offset: int) -> list[Episode]: ...

    def get_episode(self, episode_id: str | None = None, audio_url: str | None = None) -> Episode: ...

    def search_transcripts(
        self,
        query_embedding: list[float] | None,
        limit: int,
        episode_id: str | None = None,
    ) -> list[TranscriptChunk]: ...

    def get_transcript_around_timestamp(
        self,
        episode_id: str,
        timestamp_seconds: float,
        context_seconds: int,
    ) -> TranscriptContext: ...

    def search_by_speaker(
        self,
        speaker_name: str | None,
        speaker_id: str | None,
        query_embedding: list[float] | None,
        episode_id: str | None,
        limit: int,
    ) -> list[TranscriptChunk]: ...


class PostgresTranscriptRepository:
    """Transcript repository backed by Postgres with pgvector."""

    EPISODE_SELECT = """
        SELECT
            e.id,
            e.titel AS title,
            e.datum AS published_at,
            e.audio_url,
            e.duur AS duration,
            COUNT(DISTINCT ts.id) AS segment_count,
            COUNT(DISTINCT tc.start_seconds) AS chunk_count
        FROM episodes e
        LEFT JOIN transcript_segments ts ON ts.episode_id = e.id
        LEFT JOIN transcript_chunks tc ON tc.episode_id = e.id
    """

    CHUNK_SELECT = """
        SELECT
            tc.episode_id,
            e.titel AS episode_title,
            e.datum AS published_at,
            e.audio_url,
            tc.start_seconds,
            tc.end_seconds,
            tc.speaker_id,
            tc.speaker_name,
            tc.speaker_confidence,
            tc.text
    """

    def list_episodes(self, limit: int, offset: int) -> list[Episode]:
        with _cursor() as cursor:
            cursor.execute(
                self.EPISODE_SELECT
                + """
                GROUP BY e.id
                ORDER BY e.datum DESC NULLS LAST, e.titel
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            return [self._episode_from_row(row) for row in cursor.fetchall()]

    def get_episode(self, episode_id: str | None = None, audio_url: str | None = None) -> Episode:
        if not episode_id and not audio_url:
            raise ValueError("Provide episode_id or audio_url")

        where_clause = "e.id = %s" if episode_id else "e.audio_url = %s"
        value = episode_id or audio_url

        with _cursor() as cursor:
            cursor.execute(
                self.EPISODE_SELECT
                + f"""
                WHERE {where_clause}
                GROUP BY e.id
                """,
                (value,),
            )
            row = cursor.fetchone()
            if row is None:
                raise LookupError("Episode not found")

            cursor.execute(
                """
                SELECT speaker_id, speaker_name, speaker_confidence, evidence
                FROM episode_speakers
                WHERE episode_id = %s
                ORDER BY speaker_id
                """,
                (row["id"],),
            )
            speakers = [
                Speaker(
                    speaker_id=str(speaker["speaker_id"]),
                    speaker_name=speaker["speaker_name"],
                    speaker_confidence=float(speaker["speaker_confidence"])
                    if speaker["speaker_confidence"] is not None
                    else None,
                    evidence=speaker["evidence"],
                )
                for speaker in cursor.fetchall()
            ]

        episode = self._episode_from_row(row)
        episode.speakers = speakers
        return episode

    def search_transcripts(
        self,
        query_embedding: list[float] | None,
        limit: int,
        episode_id: str | None = None,
    ) -> list[TranscriptChunk]:
        if query_embedding is None:
            raise ValueError("query_embedding is required for semantic search")

        filters = []
        values: list[Any] = []
        if episode_id:
            filters.append("tc.episode_id = %s")
            values.append(episode_id)

        where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""

        embedding_literal = vector_literal(query_embedding)
        with _cursor() as cursor:
            cursor.execute(
                self.CHUNK_SELECT
                + f"""
                , 1 - (tc.embedding <=> %s::vector) AS similarity
            FROM transcript_chunks tc
            JOIN episodes e ON e.id = tc.episode_id
            {where_sql}
            ORDER BY tc.embedding <=> %s::vector
            LIMIT %s
            """,
                [embedding_literal, *values, embedding_literal, limit],
            )
            return [self._chunk_from_row(row) for row in cursor.fetchall()]

    def get_transcript_around_timestamp(
        self,
        episode_id: str,
        timestamp_seconds: float,
        context_seconds: int,
    ) -> TranscriptContext:
        start = max(0, timestamp_seconds - context_seconds)
        end = timestamp_seconds + context_seconds

        with _cursor() as cursor:
            cursor.execute(
                """
                SELECT id, titel AS title, datum AS published_at, audio_url, duur AS duration
                FROM episodes
                WHERE id = %s
                """,
                (episode_id,),
            )
            episode_row = cursor.fetchone()
            if episode_row is None:
                raise LookupError("Episode not found")

            cursor.execute(
                """
                SELECT
                    start_seconds,
                    end_seconds,
                    speaker_id,
                    speaker_name,
                    speaker_confidence,
                    diarization_confidence,
                    text
                FROM transcript_segments
                WHERE episode_id = %s
                  AND end_seconds >= %s
                  AND start_seconds <= %s
                ORDER BY start_seconds
                """,
                (episode_id, start, end),
            )
            segments = [self._segment_from_row(row) for row in cursor.fetchall()]

        return TranscriptContext(
            episode=row_dict(episode_row),
            timestamp_seconds=timestamp_seconds,
            context_start_seconds=start,
            context_end_seconds=end,
            segments=segments,
        )

    def search_by_speaker(
        self,
        speaker_name: str | None,
        speaker_id: str | None,
        query_embedding: list[float] | None,
        episode_id: str | None,
        limit: int,
    ) -> list[TranscriptChunk]:
        if not speaker_name and not speaker_id:
            raise ValueError("Provide speaker_name or speaker_id")

        filters = []
        values: list[Any] = []
        if speaker_id:
            filters.append("tc.speaker_id = %s")
            values.append(speaker_id)
        if speaker_name:
            filters.append("tc.speaker_name ILIKE %s")
            values.append(f"%{speaker_name}%")
        if episode_id:
            filters.append("tc.episode_id = %s")
            values.append(episode_id)

        where_sql = "WHERE " + " AND ".join(filters)

        with _cursor() as cursor:
            if query_embedding is not None:
                embedding_literal = vector_literal(query_embedding)
                cursor.execute(
                    self.CHUNK_SELECT
                    + f"""
                    , 1 - (tc.embedding <=> %s::vector) AS similarity
                FROM transcript_chunks tc
                JOIN episodes e ON e.id = tc.episode_id
                {where_sql}
                ORDER BY tc.embedding <=> %s::vector
                LIMIT %s
                """,
                    [embedding_literal, *values, embedding_literal, limit],
                )
            else:
                cursor.execute(
                    self.CHUNK_SELECT
                    + f"""
                FROM transcript_chunks tc
                JOIN episodes e ON e.id = tc.episode_id
                {where_sql}
                ORDER BY e.datum DESC NULLS LAST, tc.start_seconds
                LIMIT %s
                """,
                    [*values, limit],
                )

            return [self._chunk_from_row(row) for row in cursor.fetchall()]

    @staticmethod
    def _episode_from_row(row: dict[str, Any]) -> Episode:
        return Episode(
            id=str(row["id"]),
            title=row["title"],
            published_at=row["published_at"],
            audio_url=row["audio_url"],
            duration=row["duration"],
            segment_count=row["segment_count"],
            chunk_count=row["chunk_count"],
        )

    @staticmethod
    def _chunk_from_row(row: dict[str, Any]) -> TranscriptChunk:
        return TranscriptChunk(
            text=row["text"],
            start_seconds=float(row["start_seconds"]),
            end_seconds=float(row["end_seconds"]),
            speaker_id=row["speaker_id"],
            speaker_name=row["speaker_name"],
            speaker_confidence=float(row["speaker_confidence"]) if row["speaker_confidence"] is not None else None,
            similarity=float(row["similarity"]) if row.get("similarity") is not None else None,
            episode_id=str(row["episode_id"]) if row.get("episode_id") else None,
            episode_title=row.get("episode_title"),
            published_at=row.get("published_at"),
            audio_url=row.get("audio_url"),
        )

    @staticmethod
    def _segment_from_row(row: dict[str, Any]) -> TranscriptSegment:
        return TranscriptSegment(
            text=row["text"],
            start_seconds=float(row["start_seconds"]),
            end_seconds=float(row["end_seconds"]),
            speaker_id=row["speaker_id"],
            speaker_name=row["speaker_name"],
            speaker_confidence=float(row["speaker_confidence"]) if row["speaker_confidence"] is not None else None,
            diarization_confidence=float(row["diarization_confidence"])
            if row["diarization_confidence"] is not None
            else None,
        )