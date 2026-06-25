#!/usr/bin/env python3
import argparse
import json
import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
from dotenv import load_dotenv

from podcast_mcp.ingest.transcript import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    embed_texts,
    vector_literal,
)


DEFAULT_SEARCH_LIMIT = 5
DEFAULT_AROUND_CONTEXT_SECONDS = 60


def database_url() -> str:
    value = os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL missing. Add it to .env or export it.")
    return value


def embedding_config() -> tuple[str, int]:
    return (
        os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        DEFAULT_EMBEDDING_DIMENSIONS,
    )


def query_embedding(query: str) -> str:
    model, dimensions = embedding_config()
    embedding = embed_texts([query], model, dimensions, batch_size=1)[0]
    return vector_literal(embedding)


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


def list_episodes(limit: int = 25, offset: int = 0) -> list[dict[str, Any]]:
    with psycopg.connect(database_url(), row_factory=psycopg.rows.dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
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
                GROUP BY e.id
                ORDER BY e.datum DESC NULLS LAST, e.titel
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            return [row_dict(row) for row in cursor.fetchall()]


def get_episode(episode_id: str | None = None, audio_url: str | None = None) -> dict[str, Any]:
    if not episode_id and not audio_url:
        raise ValueError("Provide episode_id or audio_url")

    where_clause = "e.id = %s" if episode_id else "e.audio_url = %s"
    value = episode_id or audio_url

    with psycopg.connect(database_url(), row_factory=psycopg.rows.dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
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
                WHERE {where_clause}
                GROUP BY e.id
                """,
                (value,),
            )
            episode = cursor.fetchone()
            if episode is None:
                raise LookupError("Episode not found")

            cursor.execute(
                """
                SELECT speaker_id, speaker_name, speaker_confidence, evidence
                FROM episode_speakers
                WHERE episode_id = %s
                ORDER BY speaker_id
                """,
                (episode["id"],),
            )
            speakers = [row_dict(row) for row in cursor.fetchall()]

    return {**row_dict(episode), "speakers": speakers}


def search_podcast_transcripts(
    query: str,
    limit: int = DEFAULT_SEARCH_LIMIT,
    episode_id: str | None = None,
) -> list[dict[str, Any]]:
    embedding = query_embedding(query)
    filters = []
    values: list[Any] = []
    if episode_id:
        filters.append("tc.episode_id = %s")
        values.append(episode_id)

    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""

    with psycopg.connect(database_url(), row_factory=psycopg.rows.dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
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
                    tc.text,
                    1 - (tc.embedding <=> %s::vector) AS similarity
                FROM transcript_chunks tc
                JOIN episodes e ON e.id = tc.episode_id
                {where_sql}
                ORDER BY tc.embedding <=> %s::vector
                LIMIT %s
                """,
                [embedding, *values, embedding, limit],
            )
            return [row_dict(row) for row in cursor.fetchall()]


def get_transcript_around_timestamp(
    episode_id: str,
    timestamp_seconds: float,
    context_seconds: int = DEFAULT_AROUND_CONTEXT_SECONDS,
) -> dict[str, Any]:
    start = max(0, timestamp_seconds - context_seconds)
    end = timestamp_seconds + context_seconds

    with psycopg.connect(database_url(), row_factory=psycopg.rows.dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, titel AS title, datum AS published_at, audio_url, duur AS duration
                FROM episodes
                WHERE id = %s
                """,
                (episode_id,),
            )
            episode = cursor.fetchone()
            if episode is None:
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
            segments = [row_dict(row) for row in cursor.fetchall()]

    return {
        "episode": row_dict(episode),
        "timestamp_seconds": timestamp_seconds,
        "context_start_seconds": start,
        "context_end_seconds": end,
        "segments": segments,
    }


def search_by_speaker(
    speaker_name: str | None = None,
    speaker_id: str | None = None,
    query: str | None = None,
    episode_id: str | None = None,
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> list[dict[str, Any]]:
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

    with psycopg.connect(database_url(), row_factory=psycopg.rows.dict_row) as connection:
        with connection.cursor() as cursor:
            if query:
                embedding = query_embedding(query)
                cursor.execute(
                    f"""
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
                        tc.text,
                        1 - (tc.embedding <=> %s::vector) AS similarity
                    FROM transcript_chunks tc
                    JOIN episodes e ON e.id = tc.episode_id
                    {where_sql}
                    ORDER BY tc.embedding <=> %s::vector
                    LIMIT %s
                    """,
                    [embedding, *values, embedding, limit],
                )
            else:
                cursor.execute(
                    f"""
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
                    FROM transcript_chunks tc
                    JOIN episodes e ON e.id = tc.episode_id
                    {where_sql}
                    ORDER BY e.datum DESC NULLS LAST, tc.start_seconds
                    LIMIT %s
                    """,
                    [*values, limit],
                )

            return [row_dict(row) for row in cursor.fetchall()]


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Query podcast transcript tools from the command line.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list-episodes")
    list_parser.add_argument("--limit", type=int, default=25)
    list_parser.add_argument("--offset", type=int, default=0)

    episode_parser = subparsers.add_parser("get-episode")
    episode_parser.add_argument("--episode-id")
    episode_parser.add_argument("--audio-url")

    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("query")
    search_parser.add_argument("--limit", type=int, default=DEFAULT_SEARCH_LIMIT)
    search_parser.add_argument("--episode-id")

    around_parser = subparsers.add_parser("around")
    around_parser.add_argument("episode_id")
    around_parser.add_argument("timestamp_seconds", type=float)
    around_parser.add_argument("--context-seconds", type=int, default=DEFAULT_AROUND_CONTEXT_SECONDS)

    speaker_parser = subparsers.add_parser("speaker")
    speaker_parser.add_argument("--speaker-name")
    speaker_parser.add_argument("--speaker-id")
    speaker_parser.add_argument("--query")
    speaker_parser.add_argument("--episode-id")
    speaker_parser.add_argument("--limit", type=int, default=DEFAULT_SEARCH_LIMIT)

    args = parser.parse_args()

    if args.command == "list-episodes":
        print_json(list_episodes(args.limit, args.offset))
    elif args.command == "get-episode":
        print_json(get_episode(args.episode_id, args.audio_url))
    elif args.command == "search":
        print_json(search_podcast_transcripts(args.query, args.limit, args.episode_id))
    elif args.command == "around":
        print_json(get_transcript_around_timestamp(args.episode_id, args.timestamp_seconds, args.context_seconds))
    elif args.command == "speaker":
        print_json(search_by_speaker(args.speaker_name, args.speaker_id, args.query, args.episode_id, args.limit))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
