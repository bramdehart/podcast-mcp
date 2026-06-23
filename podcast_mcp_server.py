#!/usr/bin/env python3
import hmac
import os
from typing import Any

from dotenv import load_dotenv
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP

from podcast_tools import (
    get_episode as get_episode_data,
    get_transcript_around_timestamp as get_transcript_around_timestamp_data,
    list_episodes as list_episodes_data,
    search_by_speaker as search_by_speaker_data,
    search_podcast_transcripts as search_podcast_transcripts_data,
)


load_dotenv()


DEFAULT_MCP_HOST = "127.0.0.1"
DEFAULT_MCP_PORT = 8000
DEFAULT_MCP_PUBLIC_URL = "http://localhost:8000"


class StaticBearerTokenVerifier(TokenVerifier):
    def __init__(self, token: str) -> None:
        self.token = token

    async def verify_token(self, token: str) -> AccessToken | None:
        if not hmac.compare_digest(token, self.token):
            return None
        return AccessToken(token=token, client_id="podcast-rag", scopes=["mcp"])


def int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def create_mcp_server() -> FastMCP:
    bearer_token = os.getenv("MCP_BEARER_TOKEN")
    public_url = os.getenv("MCP_PUBLIC_URL", DEFAULT_MCP_PUBLIC_URL)
    auth_settings = None
    token_verifier = None

    if bearer_token:
        auth_settings = AuthSettings(issuer_url=public_url, resource_server_url=public_url)
        token_verifier = StaticBearerTokenVerifier(bearer_token)

    return FastMCP(
        "podcast-rag",
        auth=auth_settings,
        token_verifier=token_verifier,
        host=os.getenv("MCP_HOST", DEFAULT_MCP_HOST),
        port=int_env("MCP_PORT", DEFAULT_MCP_PORT),
    )


mcp = create_mcp_server()


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
    transport = os.getenv("MCP_TRANSPORT", "stdio").strip().lower()
    if transport != "stdio" and not os.getenv("MCP_BEARER_TOKEN"):
        raise SystemExit("MCP_BEARER_TOKEN is required when MCP_TRANSPORT is not stdio")
    if transport not in {"stdio", "sse", "streamable-http"}:
        raise SystemExit("MCP_TRANSPORT must be 'stdio', 'sse', or 'streamable-http'")
    mcp.run(transport=transport)
