"""Domain models for speakers and speaker attribution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Speaker:
    speaker_id: str
    speaker_name: str | None = None
    speaker_confidence: float | None = None
    evidence: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "speaker_id": self.speaker_id,
            "speaker_name": self.speaker_name,
            "speaker_confidence": self.speaker_confidence,
            "evidence": self.evidence,
        }