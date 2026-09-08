"""Domain models for podcast episodes and their metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from podcast_mcp.domain.speaker import Speaker


@dataclass
class Episode:
    id: str
    title: str
    published_at: datetime | None = None
    audio_url: str | None = None
    duration: int | None = None
    segment_count: int | None = None
    chunk_count: int | None = None
    speakers: list[Speaker] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "audio_url": self.audio_url,
            "duration": self.duration,
            "segment_count": self.segment_count,
            "chunk_count": self.chunk_count,
            "speakers": [speaker.to_dict() for speaker in self.speakers],
        }