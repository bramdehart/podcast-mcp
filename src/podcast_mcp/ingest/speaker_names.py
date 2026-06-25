#!/usr/bin/env python3
import argparse
import os
import sys
import time
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from podcast_mcp.ingest.rss import DEFAULT_RSS_URL, fetch_rss_xml, parse_episode_items
from podcast_mcp.runpod.client import resolve_speaker_names_locally
from podcast_mcp.transcribe.pipeline import DEFAULT_SPEAKER_NAME_MODEL


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def episode_metadata_by_audio_url() -> dict[str, dict[str, Any]]:
    rss_url = os.getenv("RSS_URL", DEFAULT_RSS_URL)
    try:
        return {str(episode["audio_url"]): episode for episode in parse_episode_items(fetch_rss_xml(rss_url))}
    except Exception as error:
        log(f"RSS metadata unavailable for speaker-name context: {error}")
        return {}


def select_episodes(
    connection: psycopg.Connection[Any],
    episode_id: str | None,
    include_named: bool,
    limit: int | None,
) -> list[dict[str, Any]]:
    where = []
    values: list[Any] = []
    if episode_id:
        where.append("e.id = %s")
        values.append(episode_id)
    if not include_named:
        where.append(
            """
            EXISTS (
                SELECT 1
                FROM episode_speakers es
                WHERE es.episode_id = e.id
                  AND es.speaker_id IS NOT NULL
                  AND (es.speaker_name IS NULL OR es.speaker_name = '')
            )
            """
        )

    query = """
        SELECT e.id, e.titel AS title, e.audio_url
        FROM episodes e
    """
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY e.datum DESC NULLS LAST, e.titel"
    if limit:
        query += " LIMIT %s"
        values.append(limit)

    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query, values)
        return list(cursor.fetchall())


def load_segments(connection: psycopg.Connection[Any], episode_id: str) -> list[dict[str, Any]]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT id, text, start_seconds, end_seconds, speaker_id
            FROM transcript_segments
            WHERE episode_id = %s
              AND speaker_id IS NOT NULL
            ORDER BY start_seconds, end_seconds
            """,
            (episode_id,),
        )
        return [
            {
                "id": str(row["id"]),
                "text": row["text"],
                "start": float(row["start_seconds"]),
                "end": float(row["end_seconds"]),
                "speaker_id": row["speaker_id"],
                "speaker_name": None,
                "speaker_confidence": None,
            }
            for row in cursor.fetchall()
        ]


def named_mapping(speaker_mapping: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    return {
        speaker_id: value
        for speaker_id, value in speaker_mapping.items()
        if value.get("speaker_name")
    }


def update_episode_mapping(
    connection: psycopg.Connection[Any],
    episode_id: str,
    speaker_mapping: dict[str, dict[str, object]],
) -> None:
    with connection.cursor() as cursor:
        for speaker_id, value in speaker_mapping.items():
            speaker_name = value.get("speaker_name")
            speaker_confidence = value.get("speaker_confidence")
            evidence = value.get("evidence")
            cursor.execute(
                """
                INSERT INTO episode_speakers (
                    episode_id,
                    speaker_id,
                    speaker_name,
                    speaker_confidence,
                    evidence
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (episode_id, speaker_id)
                DO UPDATE
                SET speaker_name = EXCLUDED.speaker_name,
                    speaker_confidence = EXCLUDED.speaker_confidence,
                    evidence = EXCLUDED.evidence
                """,
                (episode_id, speaker_id, speaker_name, speaker_confidence, evidence),
            )

            cursor.execute(
                """
                UPDATE transcript_segments
                SET speaker_name = %s,
                    speaker_confidence = %s
                WHERE episode_id = %s
                  AND speaker_id = %s
                """,
                (speaker_name, speaker_confidence, episode_id, speaker_id),
            )

            cursor.execute(
                """
                UPDATE transcript_chunks
                SET speaker_name = %s,
                    speaker_confidence = %s
                WHERE episode_id = %s
                  AND speaker_id = %s
                """,
                (speaker_name, speaker_confidence, episode_id, speaker_id),
            )


def resolve_episode(
    connection: psycopg.Connection[Any],
    episode: dict[str, Any],
    metadata_by_audio_url: dict[str, dict[str, Any]],
    dry_run: bool,
) -> int:
    segments = load_segments(connection, str(episode["id"]))
    if not segments:
        log(f"Skipping '{episode['title']}': no speaker segments")
        return 0

    metadata = metadata_by_audio_url.get(str(episode["audio_url"]), {})
    transcript = {
        "diarization_enabled": True,
        "segments": segments,
    }
    resolved = resolve_speaker_names_locally(
        str(episode["audio_url"]),
        transcript,
        str(metadata["description"]) if metadata.get("description") else None,
        str(metadata["podcast_description"]) if metadata.get("podcast_description") else None,
    )
    speaker_mapping = named_mapping(resolved.get("speaker_mapping", {}))

    if not speaker_mapping:
        log(f"Resolved '{episode['title']}': 0 named speakers")
        return 0

    if dry_run:
        names = ", ".join(
            f"{speaker_id}={value.get('speaker_name')} ({value.get('speaker_confidence')})"
            for speaker_id, value in speaker_mapping.items()
        )
        log(f"Dry run '{episode['title']}': {names}")
        return len(speaker_mapping)

    update_episode_mapping(connection, str(episode["id"]), speaker_mapping)
    log(f"Updated '{episode['title']}': {len(speaker_mapping)} named speakers")
    return len(speaker_mapping)


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Resolve missing speaker names for already-ingested episodes.")
    parser.add_argument("--episode-id", help="Only resolve one episode id.")
    parser.add_argument("--limit", type=int, help="Maximum number of episodes to process.")
    parser.add_argument("--include-named", action="store_true", help="Also reprocess episodes that already have names.")
    parser.add_argument("--dry-run", action="store_true", help="Resolve names without writing database updates.")
    args = parser.parse_args()

    if os.getenv("SPEAKER_NAME_RESOLUTION_ENABLED", "").strip().lower() not in {"1", "true", "yes", "on"}:
        log("SPEAKER_NAME_RESOLUTION_ENABLED must be true")
        return 1
    if not os.getenv("OPENAI_API_KEY"):
        log("OPENAI_API_KEY missing")
        return 1

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        log("DATABASE_URL missing")
        return 1

    model = os.getenv("SPEAKER_NAME_MODEL", DEFAULT_SPEAKER_NAME_MODEL)
    started_at = time.monotonic()
    log(f"Resolving speaker names with {model}")

    metadata_by_audio_url = episode_metadata_by_audio_url()
    processed = 0
    named_speakers = 0

    with psycopg.connect(database_url) as connection:
        episodes = select_episodes(connection, args.episode_id, args.include_named, args.limit)
        for episode in episodes:
            named_speakers += resolve_episode(connection, episode, metadata_by_audio_url, args.dry_run)
            processed += 1
        if args.dry_run:
            connection.rollback()
        else:
            connection.commit()

    log(
        f"Speaker name DB resolution complete: {processed} episode(s), "
        f"{named_speakers} named speaker(s), {time.monotonic() - started_at:.1f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
