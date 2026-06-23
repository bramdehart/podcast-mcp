#!/usr/bin/env python3
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from podcast_tools import (
    get_episode as get_episode_data,
    get_transcript_around_timestamp as get_transcript_around_timestamp_data,
    list_episodes as list_episodes_data,
    search_by_speaker as search_by_speaker_data,
    search_podcast_transcripts as search_podcast_transcripts_data,
)


load_dotenv()

mcp = FastMCP("podcast-rag")


@mcp.tool()
def search_podcast_transcripts(query: str, limit: int = 5, episode_id: str | None = None) -> list[dict[str, Any]]:
    """
    Search podcast transcript chunks by semantic similarity.

    Speaker attribution guidance:
    - Treat speaker_name as certain only when speaker_confidence >= 0.85.
    - For 0.60 <= speaker_confidence < 0.85, phrase attribution as likely/probable in the user's language.
    - Below 0.60, avoid firm attribution and mention that the speaker identity is uncertain.
    """
    return search_podcast_transcripts_data(query=query, limit=limit, episode_id=episode_id)


@mcp.tool()
def get_episode(episode_id: str | None = None, audio_url: str | None = None) -> dict[str, Any]:
    """
    Get episode metadata and speaker mappings by episode id or audio URL.

    Speaker attribution guidance:
    - Treat speaker_name as certain only when speaker_confidence >= 0.85.
    - For 0.60 <= speaker_confidence < 0.85, phrase attribution as likely/probable in the user's language.
    - Below 0.60, avoid firm attribution and mention that the speaker identity is uncertain.
    """
    return get_episode_data(episode_id=episode_id, audio_url=audio_url)


@mcp.tool()
def get_transcript_around_timestamp(
    episode_id: str,
    timestamp_seconds: float,
    context_seconds: int = 60,
) -> dict[str, Any]:
    """
    Get transcript segments around a timestamp in an episode.

    Speaker attribution guidance:
    - Treat speaker_name as certain only when speaker_confidence >= 0.85.
    - For 0.60 <= speaker_confidence < 0.85, phrase attribution as likely/probable in the user's language.
    - Below 0.60, avoid firm attribution and mention that the speaker identity is uncertain.
    """
    return get_transcript_around_timestamp_data(
        episode_id=episode_id,
        timestamp_seconds=timestamp_seconds,
        context_seconds=context_seconds,
    )


@mcp.tool()
def list_episodes(limit: int = 25, offset: int = 0) -> list[dict[str, Any]]:
    """List indexed podcast episodes."""
    return list_episodes_data(limit=limit, offset=offset)


@mcp.tool()
def search_by_speaker(
    speaker_name: str | None = None,
    speaker_id: str | None = None,
    query: str | None = None,
    episode_id: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Search or list transcript chunks spoken by a speaker.

    Speaker attribution guidance:
    - Treat speaker_name as certain only when speaker_confidence >= 0.85.
    - For 0.60 <= speaker_confidence < 0.85, phrase attribution as likely/probable in the user's language.
    - Below 0.60, avoid firm attribution and mention that the speaker identity is uncertain.
    """
    return search_by_speaker_data(
        speaker_name=speaker_name,
        speaker_id=speaker_id,
        query=query,
        episode_id=episode_id,
        limit=limit,
    )


if __name__ == "__main__":
    mcp.run()
