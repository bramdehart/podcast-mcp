#!/usr/bin/env python3
import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
import requests
from dotenv import load_dotenv


DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EMBEDDING_DIMENSIONS = 1536
DEFAULT_EMBEDDING_BATCH_SIZE = 64
DEFAULT_CHUNK_MAX_CHARS = 2000
DEFAULT_CHUNK_MAX_SECONDS = 180


@dataclass
class TranscriptChunk:
    text: str
    start_seconds: float
    end_seconds: float
    speaker_id: str | None
    speaker_name: str | None
    speaker_confidence: float | None


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def load_transcript(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def seconds_to_timestamp(seconds: float) -> str:
    total_seconds = int(seconds)
    minutes, second = divmod(total_seconds, 60)
    hour, minute = divmod(minutes, 60)
    if hour:
        return f"{hour:02d}:{minute:02d}:{second:02d}"
    return f"{minute:02d}:{second:02d}"


def segment_speaker_label(segment: dict[str, Any]) -> str:
    speaker_name = segment.get("speaker_name")
    speaker_id = segment.get("speaker_id")
    if speaker_name:
        return str(speaker_name)
    if speaker_id:
        return str(speaker_id)
    return "UNKNOWN_SPEAKER"


def format_segment_for_chunk(segment: dict[str, Any]) -> str:
    start = float(segment.get("start", 0) or 0)
    end = float(segment.get("end", start) or start)
    text = str(segment.get("text", "")).strip()
    label = segment_speaker_label(segment)
    return f"[{seconds_to_timestamp(start)}-{seconds_to_timestamp(end)}] {label}: {text}"


def shared_speaker_value(segments: list[dict[str, Any]], key: str) -> Any | None:
    values = {segment.get(key) for segment in segments if segment.get(key) is not None}
    if len(values) == 1:
        return next(iter(values))
    return None


def average_confidence(segments: list[dict[str, Any]]) -> float | None:
    values = [
        float(segment["speaker_confidence"])
        for segment in segments
        if segment.get("speaker_confidence") is not None
    ]
    if not values:
        return None
    return sum(values) / len(values)


def build_chunk(segments: list[dict[str, Any]]) -> TranscriptChunk:
    start = float(segments[0].get("start", 0) or 0)
    end = float(segments[-1].get("end", start) or start)
    return TranscriptChunk(
        text="\n".join(format_segment_for_chunk(segment) for segment in segments),
        start_seconds=start,
        end_seconds=end,
        speaker_id=shared_speaker_value(segments, "speaker_id"),
        speaker_name=shared_speaker_value(segments, "speaker_name"),
        speaker_confidence=average_confidence(segments),
    )


def chunk_segments(
    segments: list[dict[str, Any]],
    max_chars: int,
    max_seconds: int,
) -> list[TranscriptChunk]:
    chunks: list[TranscriptChunk] = []
    current: list[dict[str, Any]] = []
    current_chars = 0

    for segment in segments:
        text = str(segment.get("text", "")).strip()
        if not text:
            continue

        formatted = format_segment_for_chunk(segment)
        segment_start = float(segment.get("start", 0) or 0)
        segment_end = float(segment.get("end", segment_start) or segment_start)
        current_start = float(current[0].get("start", segment_start) or segment_start) if current else segment_start
        would_exceed_chars = bool(current) and current_chars + len(formatted) + 1 > max_chars
        would_exceed_seconds = bool(current) and segment_end - current_start > max_seconds

        if would_exceed_chars or would_exceed_seconds:
            chunks.append(build_chunk(current))
            current = []
            current_chars = 0

        current.append(segment)
        current_chars += len(formatted) + 1

    if current:
        chunks.append(build_chunk(current))

    return chunks


def openai_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def embed_texts(texts: list[str], model: str, dimensions: int, batch_size: int) -> list[list[float]]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for transcript embedding")

    embeddings: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = requests.post(
            "https://api.openai.com/v1/embeddings",
            headers=openai_headers(api_key),
            json={
                "model": model,
                "input": batch,
                "dimensions": dimensions,
            },
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
        embeddings.extend(item["embedding"] for item in sorted(payload["data"], key=lambda item: item["index"]))
        log(f"Embedded {min(start + len(batch), len(texts))}/{len(texts)} chunks")

    return embeddings


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.9g}" for value in values) + "]"


def speaker_rows(transcript: dict[str, Any], segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mapping = transcript.get("speaker_mapping")
    rows: dict[str, dict[str, Any]] = {}

    if isinstance(mapping, dict):
        for speaker_id, value in mapping.items():
            if not isinstance(value, dict):
                continue
            rows[str(speaker_id)] = {
                "speaker_id": str(speaker_id),
                "speaker_name": value.get("speaker_name"),
                "speaker_confidence": value.get("speaker_confidence"),
                "evidence": value.get("evidence"),
            }

    for segment in segments:
        speaker_id = segment.get("speaker_id")
        if not speaker_id:
            continue
        speaker_id = str(speaker_id)
        rows.setdefault(
            speaker_id,
            {
                "speaker_id": speaker_id,
                "speaker_name": segment.get("speaker_name"),
                "speaker_confidence": segment.get("speaker_confidence"),
                "evidence": None,
            },
        )
        if segment.get("speaker_name") and not rows[speaker_id].get("speaker_name"):
            rows[speaker_id]["speaker_name"] = segment.get("speaker_name")
        if segment.get("speaker_confidence") is not None and rows[speaker_id].get("speaker_confidence") is None:
            rows[speaker_id]["speaker_confidence"] = segment.get("speaker_confidence")

    return list(rows.values())


def store_transcript(
    database_url: str,
    episode: dict[str, Any],
    transcript: dict[str, Any],
    chunks: list[TranscriptChunk],
    embeddings: list[list[float]],
) -> str:
    segments = transcript.get("segments")
    if not isinstance(segments, list):
        raise RuntimeError("Transcript JSON does not contain a segments array")

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO episodes (titel, datum, audio_url, duur)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (audio_url) DO UPDATE
                SET titel = EXCLUDED.titel,
                    datum = EXCLUDED.datum,
                    duur = EXCLUDED.duur
                RETURNING id
                """,
                (
                    episode["title"],
                    episode.get("published_at"),
                    transcript["audio_url"],
                    episode.get("duration") or int(float(transcript.get("duration") or 0)) or None,
                ),
            )
            episode_id = str(cursor.fetchone()[0])

            cursor.execute("DELETE FROM transcript_chunks WHERE episode_id = %s", (episode_id,))
            cursor.execute("DELETE FROM transcript_segments WHERE episode_id = %s", (episode_id,))
            cursor.execute("DELETE FROM episode_speakers WHERE episode_id = %s", (episode_id,))

            for speaker in speaker_rows(transcript, segments):
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
                    ON CONFLICT (episode_id, speaker_id) DO UPDATE
                    SET speaker_name = EXCLUDED.speaker_name,
                        speaker_confidence = EXCLUDED.speaker_confidence,
                        evidence = EXCLUDED.evidence
                    """,
                    (
                        episode_id,
                        speaker["speaker_id"],
                        speaker.get("speaker_name"),
                        speaker.get("speaker_confidence"),
                        speaker.get("evidence"),
                    ),
                )

            for segment in segments:
                cursor.execute(
                    """
                    INSERT INTO transcript_segments (
                        episode_id,
                        text,
                        start_seconds,
                        end_seconds,
                        speaker_id,
                        speaker_name,
                        speaker_confidence,
                        diarization_confidence
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        episode_id,
                        str(segment.get("text", "")).strip(),
                        segment.get("start"),
                        segment.get("end"),
                        segment.get("speaker_id"),
                        segment.get("speaker_name"),
                        segment.get("speaker_confidence"),
                        segment.get("diarization_confidence"),
                    ),
                )

            for chunk, embedding in zip(chunks, embeddings, strict=True):
                cursor.execute(
                    """
                    INSERT INTO transcript_chunks (
                        episode_id,
                        text,
                        start_seconds,
                        end_seconds,
                        embedding,
                        speaker_id,
                        speaker_name,
                        speaker_confidence
                    )
                    VALUES (%s, %s, %s, %s, %s::vector, %s, %s, %s)
                    """,
                    (
                        episode_id,
                        chunk.text,
                        chunk.start_seconds,
                        chunk.end_seconds,
                        vector_literal(embedding),
                        chunk.speaker_id,
                        chunk.speaker_name,
                        chunk.speaker_confidence,
                    ),
                )

    return episode_id


def ingest_transcript_file(transcript_path: Path, episode: dict[str, Any], database_url: str) -> str:
    transcript = load_transcript(transcript_path)
    segments = transcript.get("segments")
    if not isinstance(segments, list):
        raise RuntimeError("Transcript JSON does not contain a segments array")

    chunks = chunk_segments(
        segments,
        DEFAULT_CHUNK_MAX_CHARS,
        DEFAULT_CHUNK_MAX_SECONDS,
    )
    if not chunks:
        raise RuntimeError("Transcript did not produce chunks")

    embedding_model = os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    embedding_dimensions = DEFAULT_EMBEDDING_DIMENSIONS
    embedding_batch_size = DEFAULT_EMBEDDING_BATCH_SIZE

    log(
        "Embedding transcript "
        f"chunks={len(chunks)} model='{embedding_model}' dimensions={embedding_dimensions} batch_size={embedding_batch_size}"
    )
    embeddings = embed_texts(
        [chunk.text for chunk in chunks],
        embedding_model,
        embedding_dimensions,
        embedding_batch_size,
    )
    episode_id = store_transcript(database_url, episode, transcript, chunks, embeddings)
    log(f"Stored episode {episode_id} with {len(segments)} segments and {len(chunks)} chunks")
    return episode_id


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Embed transcript JSON and store it in Postgres.")
    parser.add_argument("transcript_path", type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--audio-url", required=True)
    parser.add_argument("--published-at")
    parser.add_argument("--duration", type=int)
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL missing. Add it to .env or export it.", file=sys.stderr)
        return 1

    published_at = datetime.fromisoformat(args.published_at) if args.published_at else None
    ingest_transcript_file(
        args.transcript_path,
        {
            "title": args.title,
            "audio_url": args.audio_url,
            "published_at": published_at,
            "duration": args.duration,
        },
        database_url,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
