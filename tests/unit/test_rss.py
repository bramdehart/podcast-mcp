from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import pytest

from podcast_mcp.ingest.rss import clean_description, parse_duration, parse_episode_items

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def load_fixture() -> bytes:
    return (FIXTURES_DIR / "episode.xml").read_bytes()


def test_parse_episode_items_returns_indexable_episodes() -> None:
    episodes = parse_episode_items(load_fixture())

    assert len(episodes) == 2

    first = episodes[0]
    assert first["title"] == "Aflevering 1: AI introductie"
    assert first["audio_url"] == "https://example.com/audio/episode-1.mp3"
    assert first["duration"] == (45 * 60) + 30
    assert first["podcast_description"] == "Een test podcast over technologie en AI."
    assert first["description"] == "In deze aflevering praten we over kunstmatige intelligentie."
    assert isinstance(first["published_at"], datetime)


def test_parse_episode_items_uses_content_encoded_then_description() -> None:
    episodes = parse_episode_items(load_fixture())

    second = episodes[1]
    assert second["title"] == "Aflevering 2: Podcast zonder beschrijving"
    assert second["description"] == "Een korte beschrijving zonder HTML."
    assert second["duration"] == (1 * 3600) + (2 * 60) + 15


def test_parse_episode_items_skips_items_without_audio_url() -> None:
    episodes = parse_episode_items(load_fixture())

    titles = [episode["title"] for episode in episodes]
    assert "Aflevering zonder audio" not in titles


def test_parse_duration() -> None:
    assert parse_duration("42") == 42
    assert parse_duration("45:30") == (45 * 60) + 30
    assert parse_duration("1:02:15") == (1 * 3600) + (2 * 60) + 15
    assert parse_duration("not-a-duration") is None
    assert parse_duration(None) is None
    assert parse_duration("") is None


def test_clean_description_strips_html_and_collapses_whitespace() -> None:
    assert clean_description("<p>Hallo   <b>wereld</b></p>") == "Hallo wereld"
    assert clean_description("  ") is None
    assert clean_description(None) is None


def test_parse_episode_items_handles_empty_xml() -> None:
    with pytest.raises(ET.ParseError):
        parse_episode_items(b"")