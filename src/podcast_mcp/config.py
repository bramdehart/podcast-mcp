"""Centralized configuration for podcast_mcp.

All environment-variable parsing lives here. Modules should read from the
shared :data:`settings` instance instead of calling ``os.getenv`` directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return float(value)


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _optional_int_env(name: str, default: int | None = None) -> int | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _str_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


@dataclass
class Settings:
    """Runtime configuration loaded from the environment once."""

    # Database
    database_url: str = ""

    # RSS sync
    rss_url: str = ""
    sync_cron: str = "0 6 * * 5"
    sync_timezone: str = "Europe/Amsterdam"
    sync_max_episodes: int = 10
    sync_max_runtime_seconds: int = 19800

    # Transcription execution
    transcribe_execution: str = "local"

    # Whisper transcription
    transcribe_model: str = "medium"
    transcribe_compute_type: str = "int8"
    transcribe_device: str = "auto"
    transcribe_beam_size: int = 5
    transcribe_chunk_seconds: int = 1800
    transcribe_language: str | None = None
    transcribe_hotwords: str | None = None

    # Speaker diarization
    diarization_enabled: bool = False
    diarization_model: str = "pyannote/speaker-diarization-3.1"
    diarization_device: str = "auto"
    diarization_min_speakers: int | None = 2
    diarization_max_speakers: int | None = 4
    huggingface_token: str | None = None

    # Speaker name resolution
    speaker_name_resolution_enabled: bool = False
    speaker_name_model: str = "gpt-5.4-mini"
    openai_api_key: str | None = None

    # Embeddings
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_batch_size: int = 64

    # RunPod
    runpod_api_key: str | None = None
    runpod_endpoint_id: str | None = None
    runpod_poll_interval_seconds: int = 10
    runpod_execution_timeout_ms: int = 1800000
    runpod_ttl_ms: int = 3600000

    # MCP server
    mcp_transport: str = "stdio"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8000
    mcp_public_url: str = "http://localhost:8000"
    mcp_bearer_token: str | None = None
    mcp_rate_limit_requests: int = 60
    mcp_rate_limit_window_seconds: int = 60

    # Chunking
    chunk_max_chars: int = 2000
    chunk_max_seconds: int = 180

    def require_database_url(self) -> str:
        if not self.database_url:
            raise RuntimeError("DATABASE_URL missing. Add it to .env or export it.")
        return self.database_url

    def require_openai_api_key(self) -> str:
        if not self.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY missing. Add it to .env or export it.")
        return self.openai_api_key

    def require_huggingface_token(self) -> str:
        if not self.huggingface_token:
            raise RuntimeError("HUGGINGFACE_TOKEN or HF_TOKEN is required when DIARIZATION_ENABLED=true")
        return self.huggingface_token


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        database_url=_str_env("DATABASE_URL", "") or "",
        rss_url=_str_env("RSS_URL", "") or "",
        sync_cron=_str_env("SYNC_CRON", "0 6 * * 5") or "0 6 * * 5",
        sync_timezone=_str_env("SYNC_TIMEZONE", "Europe/Amsterdam") or "Europe/Amsterdam",
        sync_max_episodes=_int_env("SYNC_MAX_EPISODES", 10),
        sync_max_runtime_seconds=_int_env("SYNC_MAX_RUNTIME_SECONDS", 19800),
        transcribe_execution=(_str_env("TRANSCRIBE_EXECUTION", "local") or "local").strip().lower(),
        transcribe_model=_str_env("TRANSCRIBE_MODEL", "medium") or "medium",
        transcribe_compute_type=_str_env("TRANSCRIBE_COMPUTE_TYPE", "int8") or "int8",
        transcribe_device=_str_env("TRANSCRIBE_DEVICE", "auto") or "auto",
        transcribe_beam_size=_int_env("TRANSCRIBE_BEAM_SIZE", 5),
        transcribe_chunk_seconds=_int_env("TRANSCRIBE_CHUNK_SECONDS", 1800),
        transcribe_language=_str_env("TRANSCRIBE_LANGUAGE"),
        transcribe_hotwords=_str_env("TRANSCRIBE_HOTWORDS"),
        diarization_enabled=_bool_env("DIARIZATION_ENABLED", False),
        diarization_model=_str_env("DIARIZATION_MODEL", "pyannote/speaker-diarization-3.1")
        or "pyannote/speaker-diarization-3.1",
        diarization_device=_str_env("DIARIZATION_DEVICE", "auto") or "auto",
        diarization_min_speakers=_optional_int_env("DIARIZATION_MIN_SPEAKERS", 2),
        diarization_max_speakers=_optional_int_env("DIARIZATION_MAX_SPEAKERS", 4),
        huggingface_token=_str_env("HUGGINGFACE_TOKEN") or _str_env("HF_TOKEN"),
        speaker_name_resolution_enabled=_bool_env("SPEAKER_NAME_RESOLUTION_ENABLED", False),
        speaker_name_model=_str_env("SPEAKER_NAME_MODEL", "gpt-5.4-mini") or "gpt-5.4-mini",
        openai_api_key=_str_env("OPENAI_API_KEY"),
        embedding_model=_str_env("EMBEDDING_MODEL", "text-embedding-3-small") or "text-embedding-3-small",
        embedding_dimensions=_int_env("EMBEDDING_DIMENSIONS", 1536),
        embedding_batch_size=_int_env("EMBEDDING_BATCH_SIZE", 64),
        runpod_api_key=_str_env("RUNPOD_API_KEY"),
        runpod_endpoint_id=_str_env("RUNPOD_ENDPOINT_ID"),
        runpod_poll_interval_seconds=_int_env("RUNPOD_POLL_INTERVAL_SECONDS", 10),
        runpod_execution_timeout_ms=_int_env("RUNPOD_EXECUTION_TIMEOUT_MS", 1800000),
        runpod_ttl_ms=_int_env("RUNPOD_TTL_MS", 3600000),
        mcp_transport=(_str_env("MCP_TRANSPORT", "stdio") or "stdio").strip().lower(),
        mcp_host=_str_env("MCP_HOST", "127.0.0.1") or "127.0.0.1",
        mcp_port=_int_env("MCP_PORT", 8000),
        mcp_public_url=_str_env("MCP_PUBLIC_URL", "http://localhost:8000") or "http://localhost:8000",
        mcp_bearer_token=_str_env("MCP_BEARER_TOKEN"),
        mcp_rate_limit_requests=_int_env("MCP_RATE_LIMIT_REQUESTS", 60),
        mcp_rate_limit_window_seconds=_int_env("MCP_RATE_LIMIT_WINDOW_SECONDS", 60),
        chunk_max_chars=_int_env("CHUNK_MAX_CHARS", 2000),
        chunk_max_seconds=_int_env("CHUNK_MAX_SECONDS", 180),
    )


settings = load_settings()
