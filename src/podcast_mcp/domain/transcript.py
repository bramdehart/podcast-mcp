"""Domain models for transcripts, segments, and search results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class TranscriptSegment:
    text: str
    start_seconds: float
    end_seconds: float
    speaker_id: str | None = None
    speaker_name: str | None = None
    speaker_confidence: float | None = None
    diarization_confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "speaker_id": self.speaker_id,
            "speaker_name": self.speaker_name,
            "speaker_confidence": self.speaker_confidence,
            "diarization_confidence": self.diarization_confidence,
        }


@dataclass
class TranscriptChunk:
    text: str
    start_seconds: float
    end_seconds: float
    speaker_id: str | None = None
    speaker_name: str | None = None
    speaker_confidence: float | None = None
    similarity: float | None = None
    episode_id: str | None = None
    episode_title: str | None = None
    published_at: datetime | None = None
    audio_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "speaker_id": self.speaker_id,
            "speaker_name": self.speaker_name,
            "speaker_confidence": self.speaker_confidence,
            "similarity": self.similarity,
            "episode_id": self.episode_id,
            "episode_title": self.episode_title,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "audio_url": self.audio_url,
        }


@dataclass
class TranscriptContext:
    episode: Any
    timestamp_seconds: float
    context_start_seconds: float
    context_end_seconds: float
    segments: list[TranscriptSegment]

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode": self.episode,
            "timestamp_seconds": self.timestamp_seconds,
            "context_start_seconds": self.context_start_seconds,
            "context_end_seconds": self.context_end_seconds,
            "segments": [segment.to_dict() for segment in self.segments],
        }