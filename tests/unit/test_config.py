from __future__ import annotations

from podcast_mcp.config import Settings


def test_settings_defaults() -> None:
    settings = Settings()

    assert settings.mcp_transport == "stdio"
    assert settings.mcp_port == 8000
    assert settings.sync_cron == "0 6 * * 5"
    assert settings.embedding_model == "text-embedding-3-small"
    assert settings.diarization_enabled is False


def test_require_database_url_raises_when_missing() -> None:
    settings = Settings()
    try:
        settings.require_database_url()
    except RuntimeError as error:
        assert "DATABASE_URL" in str(error)
    else:
        raise AssertionError("expected RuntimeError")


def test_require_openai_api_key_raises_when_missing() -> None:
    settings = Settings()
    try:
        settings.require_openai_api_key()
    except RuntimeError as error:
        assert "OPENAI_API_KEY" in str(error)
    else:
        raise AssertionError("expected RuntimeError")