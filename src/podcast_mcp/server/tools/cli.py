#!/usr/bin/env python3
import argparse
import json
from typing import Any

from podcast_mcp.server.tools.episodes import get_episode, list_episodes
from podcast_mcp.server.tools.search import (
    DEFAULT_AROUND_CONTEXT_SECONDS,
    DEFAULT_SEARCH_LIMIT,
    get_transcript_around_timestamp,
    search_podcast_transcripts,
)
from podcast_mcp.server.tools.speakers import search_by_speaker


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