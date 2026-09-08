#!/usr/bin/env python3
import argparse
import json
from typing import Any

from podcast_mcp.application.episodes import EpisodeService
from podcast_mcp.application.search import TranscriptSearch
from podcast_mcp.application.speakers import SpeakerService
from podcast_mcp.infrastructure.embeddings import OpenAIEmbeddingClient
from podcast_mcp.infrastructure.postgres import PostgresTranscriptRepository


DEFAULT_SEARCH_LIMIT = 5
DEFAULT_AROUND_CONTEXT_SECONDS = 60


def _episode_service() -> EpisodeService:
    return EpisodeService(PostgresTranscriptRepository())


def _search_service() -> TranscriptSearch:
    return TranscriptSearch(PostgresTranscriptRepository(), OpenAIEmbeddingClient())


def _speaker_service() -> SpeakerService:
    return SpeakerService(PostgresTranscriptRepository(), OpenAIEmbeddingClient())


def list_episodes(limit: int = 25, offset: int = 0) -> list[dict[str, Any]]:
    return [episode.to_dict() for episode in _episode_service().list_episodes(limit, offset)]


def get_episode(episode_id: str | None = None, audio_url: str | None = None) -> dict[str, Any]:
    return _episode_service().get_episode(episode_id, audio_url).to_dict()


def search_podcast_transcripts(
    query: str,
    limit: int = DEFAULT_SEARCH_LIMIT,
    episode_id: str | None = None,
) -> list[dict[str, Any]]:
    chunks = _search_service().search(query, limit, episode_id)
    return [chunk.to_dict() for chunk in chunks]


def get_transcript_around_timestamp(
    episode_id: str,
    timestamp_seconds: float,
    context_seconds: int = DEFAULT_AROUND_CONTEXT_SECONDS,
) -> dict[str, Any]:
    return _search_service().around_timestamp(episode_id, timestamp_seconds, context_seconds).to_dict()


def search_by_speaker(
    speaker_name: str | None = None,
    speaker_id: str | None = None,
    query: str | None = None,
    episode_id: str | None = None,
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> list[dict[str, Any]]:
    chunks = _speaker_service().search(speaker_name, speaker_id, query, episode_id, limit)
    return [chunk.to_dict() for chunk in chunks]


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def main() -> int:
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
