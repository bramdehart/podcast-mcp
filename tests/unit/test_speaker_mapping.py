from __future__ import annotations

import pytest

from podcast_mcp.ingest.speaker_names import named_mapping
from podcast_mcp.ingest.transcription import apply_speaker_mapping, parse_json_object


def test_parse_json_object_accepts_plain_json() -> None:
    parsed = parse_json_object('{"SPEAKER_00": {"speaker_name": "Alexander"}}')
    assert parsed["SPEAKER_00"]["speaker_name"] == "Alexander"


def test_parse_json_object_extracts_object_from_markdown() -> None:
    value = '```json\n{"SPEAKER_00": {"speaker_name": "Alexander"}}\n```'
    parsed = parse_json_object(value)
    assert parsed["SPEAKER_00"]["speaker_name"] == "Alexander"


def test_parse_json_object_rejects_non_object() -> None:
    with pytest.raises(ValueError):
        parse_json_object('["not", "an", "object"]')


def test_apply_speaker_mapping_sets_names_and_confidence() -> None:
    segments = [
        {
            "start": 0.0,
            "end": 5.0,
            "text": "Hallo",
            "speaker_id": "SPEAKER_00",
            "speaker_confidence": 0.5,
        }
    ]
    mapping = {"SPEAKER_00": {"speaker_name": "Alexander", "speaker_confidence": 0.9}}

    resolved = apply_speaker_mapping(segments, mapping)

    assert resolved[0]["speaker_name"] == "Alexander"
    assert resolved[0]["speaker_confidence"] == 0.9


def test_apply_speaker_mapping_keeps_segment_confidence_when_unmapped() -> None:
    segments = [
        {
            "start": 0.0,
            "end": 5.0,
            "text": "Hallo",
            "speaker_id": "SPEAKER_00",
            "speaker_confidence": 0.5,
        }
    ]
    mapping = {"SPEAKER_00": {"speaker_name": None, "speaker_confidence": 0.0}}

    resolved = apply_speaker_mapping(segments, mapping)

    assert resolved[0]["speaker_name"] is None
    assert resolved[0]["speaker_confidence"] == 0.5


def test_named_mapping_filters_unnamed_speakers() -> None:
    mapping = {
        "SPEAKER_00": {"speaker_name": "Alexander", "speaker_confidence": 0.9},
        "SPEAKER_01": {"speaker_name": None, "speaker_confidence": 0.1},
        "SPEAKER_02": {"speaker_name": "", "speaker_confidence": 0.0},
    }

    named = named_mapping(mapping)

    assert set(named) == {"SPEAKER_00"}