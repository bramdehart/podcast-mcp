from __future__ import annotations

from datetime import datetime

import pytest

from podcast_mcp.application.episodes import EpisodeService
from podcast_mcp.application.search import TranscriptSearch
from podcast_mcp.application.speakers import SpeakerService
from podcast_mcp.domain.episode import Episode
from podcast_mcp.domain.speaker import Speaker
from podcast_mcp.domain.transcript import TranscriptChunk, TranscriptContext, TranscriptSegment


class FakeEmbeddings:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [[0.0] * 3 for _ in texts]


class FakeRepository:
    def __init__(self) -> None:
        self.episodes = [
            Episode(
                id="11111111-1111-1111-1111-111111111111",
                title="Test episode",
                published_at=datetime(2026, 1, 5),
                audio_url="https://example.com/audio/episode-1.mp3",
                duration=2730,
                segment_count=10,
                chunk_count=4,
                speakers=[Speaker(speaker_id="SPEAKER_00", speaker_name="Alexander", speaker_confidence=0.9)],
            )
        ]

    def list_episodes(self, limit: int, offset: int) -> list[Episode]:
        return self.episodes[offset : offset + limit]

    def get_episode(self, episode_id: str | None = None, audio_url: str | None = None) -> Episode:
        for episode in self.episodes:
            if episode.id == episode_id or episode.audio_url == audio_url:
                return episode
        raise LookupError("Episode not found")

    def search_transcripts(
        self,
        query_embedding: list[float] | None,
        limit: int,
        episode_id: str | None = None,
    ) -> list[TranscriptChunk]:
        return [
            TranscriptChunk(
                text="Wat zei Alexander over Anthropic?",
                start_seconds=10.0,
                end_seconds=20.0,
                speaker_id="SPEAKER_00",
                speaker_name="Alexander",
                speaker_confidence=0.9,
                similarity=0.8,
                episode_id=self.episodes[0].id,
                episode_title=self.episodes[0].title,
                audio_url=self.episodes[0].audio_url,
            )
        ]

    def get_transcript_around_timestamp(
        self,
        episode_id: str,
        timestamp_seconds: float,
        context_seconds: int,
    ) -> TranscriptContext:
        return TranscriptContext(
            episode=self.episodes[0].to_dict(),
            timestamp_seconds=timestamp_seconds,
            context_start_seconds=0.0,
            context_end_seconds=120.0,
            segments=[
                TranscriptSegment(
                    text="Hallo",
                    start_seconds=10.0,
                    end_seconds=15.0,
                    speaker_id="SPEAKER_00",
                    speaker_name="Alexander",
                    speaker_confidence=0.9,
                )
            ],
        )

    def search_by_speaker(
        self,
        speaker_name: str | None,
        speaker_id: str | None,
        query_embedding: list[float] | None,
        episode_id: str | None,
        limit: int,
    ) -> list[TranscriptChunk]:
        return self.search_transcripts(query_embedding, limit, episode_id)


def test_list_episodes_returns_domain_objects() -> None:
    service = EpisodeService(FakeRepository())
    episodes = service.list_episodes()

    assert len(episodes) == 1
    assert episodes[0].title == "Test episode"
    assert episodes[0].speakers[0].speaker_name == "Alexander"


def test_get_episode_by_audio_url() -> None:
    service = EpisodeService(FakeRepository())
    episode = service.get_episode(audio_url="https://example.com/audio/episode-1.mp3")

    assert episode.id == "11111111-1111-1111-1111-111111111111"


def test_get_episode_missing_raises() -> None:
    service = EpisodeService(FakeRepository())
    with pytest.raises(LookupError):
        service.get_episode(audio_url="https://example.com/audio/missing.mp3")


def test_search_embeds_query_and_returns_chunks() -> None:
    embeddings = FakeEmbeddings()
    service = TranscriptSearch(FakeRepository(), embeddings)

    chunks = service.search("Anthropic", limit=5)

    assert embeddings.calls == [["Anthropic"]]
    assert len(chunks) == 1
    assert chunks[0].speaker_name == "Alexander"
    assert chunks[0].similarity == 0.8


def test_around_timestamp_returns_context() -> None:
    service = TranscriptSearch(FakeRepository(), embeddings=FakeEmbeddings())
    context = service.around_timestamp("11111111-1111-1111-1111-111111111111", 60.0, context_seconds=120)

    assert context.segments[0].speaker_name == "Alexander"
    assert context.timestamp_seconds == 60.0


def test_speaker_search_uses_query_embedding_when_provided() -> None:
    embeddings = FakeEmbeddings()
    service = SpeakerService(FakeRepository(), embeddings)

    chunks = service.search(speaker_name="Alexander", query="Anthropic")

    assert embeddings.calls == [["Anthropic"]]
    assert chunks[0].speaker_name == "Alexander"


def test_episode_to_dict_serialization() -> None:
    episode = Episode(
        id="abc",
        title="Titel",
        published_at=datetime(2026, 1, 5),
        audio_url="https://example.com/x.mp3",
        duration=100,
        speakers=[Speaker(speaker_id="S1", speaker_name="Naam", speaker_confidence=0.95)],
    )

    payload = episode.to_dict()
    assert payload["published_at"] == "2026-01-05T00:00:00"
    assert payload["speakers"][0]["speaker_name"] == "Naam"


def test_chunk_to_dict_serialization() -> None:
    chunk = TranscriptChunk(
        text="Hallo",
        start_seconds=1.0,
        end_seconds=2.0,
        speaker_name="Naam",
        speaker_confidence=0.9,
        similarity=0.7,
    )

    payload = chunk.to_dict()
    assert payload["start_seconds"] == 1.0
    assert payload["similarity"] == 0.7
    assert payload["speaker_name"] == "Naam"