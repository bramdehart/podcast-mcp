from __future__ import annotations

from podcast_mcp.ingest.transcript import build_chunk, chunk_segments, seconds_to_timestamp
from podcast_mcp.ingest.transcription import format_seconds


def segment(start: float, end: float, text: str, speaker_id: str | None = "S1") -> dict[str, object]:
    return {"start": start, "end": end, "text": text, "speaker_id": speaker_id}


def test_seconds_to_timestamp() -> None:
    assert seconds_to_timestamp(0) == "00:00"
    assert seconds_to_timestamp(59) == "00:59"
    assert seconds_to_timestamp(60) == "01:00"
    assert seconds_to_timestamp(3661) == "01:01:01"


def test_format_seconds() -> None:
    assert format_seconds(45) == "45s"
    assert format_seconds(125) == "2m 5s"
    assert format_seconds(3600 + 120 + 3) == "1h 2m 3s"


def test_chunk_segments_splits_by_char_count() -> None:
    segments = [segment(float(i), float(i + 1), "word" * 20, "S1") for i in range(10)]

    chunks = chunk_segments(segments, max_chars=100, max_seconds=3600)

    assert len(chunks) > 1
    assert sum(len(chunk.text) for chunk in chunks) > 0


def test_chunk_segments_splits_by_max_seconds() -> None:
    segments = [
        segment(0, 100, "eerste", "S1"),
        segment(100, 200, "tweede", "S1"),
        segment(200, 300, "derde", "S1"),
    ]

    chunks = chunk_segments(segments, max_chars=10000, max_seconds=150)

    assert len(chunks) >= 2


def test_chunk_segments_skips_empty_text() -> None:
    segments = [
        segment(0, 5, "   ", "S1"),
        segment(5, 10, "Hallo", "S1"),
    ]

    chunks = chunk_segments(segments, max_chars=10000, max_seconds=3600)

    assert len(chunks) == 1
    assert "Hallo" in chunks[0].text


def test_build_chunk_aggregates_speaker_and_confidence() -> None:
    segments = [
        segment(0, 5, "Een", "S1"),
        segment(5, 10, "twee", "S1"),
    ]
    for item in segments:
        item["speaker_name"] = "Alexander"
        item["speaker_confidence"] = 0.9

    chunk = build_chunk(segments)

    assert chunk.start_seconds == 0.0
    assert chunk.end_seconds == 10.0
    assert chunk.speaker_id == "S1"
    assert chunk.speaker_name == "Alexander"
    assert chunk.speaker_confidence == 0.9


def test_chunk_segments_empty_input() -> None:
    assert chunk_segments([], max_chars=100, max_seconds=60) == []