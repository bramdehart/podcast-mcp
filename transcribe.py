#!/usr/bin/env python3
import argparse
from collections import namedtuple
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

TMP_DIR = Path("/tmp")
USER_AGENT = "AppleCoreMedia"
DEFAULT_MODEL_SIZE = "medium"
DEFAULT_COMPUTE_TYPE = "int8"
DEFAULT_DEVICE = "auto"
DEFAULT_BEAM_SIZE = 1
DEFAULT_HOTWORDS = ""
DEFAULT_DIARIZATION_ENABLED = False
DEFAULT_DIARIZATION_MODEL = "pyannote/speaker-diarization-3.1"
DEFAULT_DIARIZATION_DEVICE = "auto"
DEFAULT_SPEAKER_NAME_RESOLUTION_ENABLED = False
DEFAULT_SPEAKER_NAME_MODEL = "qwen2.5:7b-instruct"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_PROGRESS_HEARTBEAT_SECONDS = 60
PROGRESS_LOG_INTERVAL_SECONDS = 300


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def format_seconds(seconds: float) -> str:
    minutes, remaining_seconds = divmod(round(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {remaining_seconds}s"
    if minutes:
        return f"{minutes}m {remaining_seconds}s"
    return f"{remaining_seconds}s"


def int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def resolve_torch_device(device: str) -> str:
    normalized_device = device.strip().lower()
    if normalized_device != "auto":
        return normalized_device

    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


def start_heartbeat(label: str, interval_seconds: int) -> tuple[threading.Event, threading.Thread | None]:
    stop_event = threading.Event()
    if interval_seconds <= 0:
        return stop_event, None

    started_at = time.monotonic()

    def log_heartbeat() -> None:
        while not stop_event.wait(interval_seconds):
            log(f"{label} still running after {format_seconds(time.monotonic() - started_at)} wall time")

    thread = threading.Thread(target=log_heartbeat, daemon=True)
    thread.start()
    return stop_event, thread


def stop_heartbeat(stop_event: threading.Event, thread: threading.Thread | None) -> None:
    stop_event.set()
    if thread is not None:
        thread.join(timeout=1)


def suffix_from_url(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix
    return suffix if suffix else ".audio"


def tmp_paths(audio_url: str) -> tuple[Path, Path]:
    audio_hash = hashlib.sha256(audio_url.encode("utf-8")).hexdigest()[:16]
    audio_path = TMP_DIR / f"podcast_audio_{audio_hash}{suffix_from_url(audio_url)}"
    transcript_path = TMP_DIR / f"podcast_transcript_{audio_hash}.json"
    return audio_path, transcript_path


def metadata_paths(audio_url: str) -> tuple[Path, Path]:
    audio_hash = hashlib.sha256(audio_url.encode("utf-8")).hexdigest()[:16]
    diarization_path = TMP_DIR / f"podcast_diarization_{audio_hash}.json"
    speaker_mapping_path = TMP_DIR / f"podcast_speaker_mapping_{audio_hash}.json"
    return diarization_path, speaker_mapping_path


def download_audio(audio_url: str, audio_path: Path) -> None:
    started_at = time.monotonic()
    log(f"Downloading audio to {audio_path}")
    subprocess.run(
        ["curl", "-fsSL", "-A", USER_AGENT, audio_url, "-o", str(audio_path)],
        check=True,
    )
    log(f"Downloaded {audio_path.stat().st_size / 1024 / 1024:.1f} MB in {format_seconds(time.monotonic() - started_at)}")


def number_value(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


def overlap_seconds(start: float, end: float, other_start: float, other_end: float) -> float:
    return max(0.0, min(end, other_end) - max(start, other_start))


def transcribe_with_faster_whisper(
    audio_path: Path,
    model_size: str,
    compute_type: str,
    device: str,
    beam_size: int,
    hotwords: str | None,
    heartbeat_seconds: int,
    language: str | None,
) -> tuple[list[dict[str, object]], object]:
    from faster_whisper import WhisperModel

    started_at = time.monotonic()
    log(f"Loading Whisper model '{model_size}' with device='{device}' compute_type='{compute_type}'")
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    log(f"Model loaded in {format_seconds(time.monotonic() - started_at)}")

    started_at = time.monotonic()
    log(
        f"Transcribing with language='{language or 'auto'}' and beam_size={beam_size} "
        f"hotwords='{hotwords or ''}'"
    )
    stop_event, heartbeat_thread = start_heartbeat("Transcription", heartbeat_seconds)
    try:
        segments, info = model.transcribe(
            str(audio_path),
            language=language,
            beam_size=beam_size,
            hotwords=hotwords,
            log_progress=True,
        )

        transcript_segments = []
        next_progress_log_at = PROGRESS_LOG_INTERVAL_SECONDS
        for segment in segments:
            transcript_segments.append(
                {
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text.strip(),
                }
            )

            while segment.end >= next_progress_log_at:
                log(f"Transcription progress: {format_seconds(next_progress_log_at)} audio processed")
                next_progress_log_at += PROGRESS_LOG_INTERVAL_SECONDS
    finally:
        stop_heartbeat(stop_event, heartbeat_thread)

    log(f"Transcribed {len(transcript_segments)} segments in {format_seconds(time.monotonic() - started_at)}")

    return transcript_segments, info


def transcribe_audio(
    audio_path: Path,
    model_size: str,
    compute_type: str,
    device: str,
    beam_size: int,
    hotwords: str | None,
    heartbeat_seconds: int,
    language: str | None,
) -> tuple[list[dict[str, object]], object]:
    return transcribe_with_faster_whisper(
        audio_path,
        model_size,
        compute_type,
        device,
        beam_size,
        hotwords,
        heartbeat_seconds,
        language,
    )


def run_diarization(
    audio_path: Path,
    diarization_model: str,
    diarization_device: str,
) -> list[dict[str, object]]:
    import soundfile
    import torch
    import torchaudio

    if not hasattr(torchaudio, "list_audio_backends"):
        torchaudio.list_audio_backends = lambda: ["soundfile"]
    if not hasattr(torchaudio, "AudioMetaData"):
        torchaudio.AudioMetaData = namedtuple(
            "AudioMetaData",
            ["sample_rate", "num_frames", "num_channels", "bits_per_sample", "encoding"],
            defaults=[0, 0, 0, 0, "UNKNOWN"],
        )
    if not hasattr(torchaudio, "info"):
        def torchaudio_info(path: object, backend: str | None = None) -> object:
            soundfile_info = soundfile.info(path)
            return torchaudio.AudioMetaData(
                sample_rate=soundfile_info.samplerate,
                num_frames=soundfile_info.frames,
                num_channels=soundfile_info.channels,
                bits_per_sample=0,
                encoding=str(soundfile_info.format),
            )

        torchaudio.info = torchaudio_info

    from pyannote.audio.core.task import Specifications
    from pyannote.audio.core.task import Problem
    from pyannote.audio.core.task import Resolution
    from pyannote.audio import Pipeline

    torch.serialization.add_safe_globals([torch.torch_version.TorchVersion, Specifications, Problem, Resolution])

    hf_token = os.getenv("HUGGINGFACE_TOKEN") or os.getenv("HF_TOKEN")
    if not hf_token:
        raise RuntimeError("HUGGINGFACE_TOKEN or HF_TOKEN is required when DIARIZATION_ENABLED=true")

    started_at = time.monotonic()
    resolved_device = resolve_torch_device(diarization_device)
    log(f"Loading pyannote diarization model '{diarization_model}' on device='{resolved_device}'")
    pipeline = Pipeline.from_pretrained(diarization_model, use_auth_token=hf_token)
    pipeline.to(torch.device(resolved_device))
    log(f"Diarization model loaded in {format_seconds(time.monotonic() - started_at)}")

    started_at = time.monotonic()
    log("Running speaker diarization")
    diarization = pipeline(str(audio_path))
    turns = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        start = float(turn.start)
        end = float(turn.end)
        if end <= start:
            continue
        turns.append(
            {
                "start": start,
                "end": end,
                "speaker_id": str(speaker),
            }
        )

    log(f"Diarized {len(turns)} speaker turns in {format_seconds(time.monotonic() - started_at)}")
    return turns


def align_segments_with_speakers(
    segments: list[dict[str, object]],
    diarization_turns: list[dict[str, object]],
) -> list[dict[str, object]]:
    aligned_segments = []
    for segment in segments:
        segment_start = number_value(segment.get("start"))
        segment_end = number_value(segment.get("end"))
        best_turn = None
        best_overlap = 0.0

        if segment_start is not None and segment_end is not None and segment_end > segment_start:
            for turn in diarization_turns:
                turn_start = number_value(turn.get("start"))
                turn_end = number_value(turn.get("end"))
                if turn_start is None or turn_end is None:
                    continue
                overlap = overlap_seconds(segment_start, segment_end, turn_start, turn_end)
                if overlap > best_overlap:
                    best_turn = turn
                    best_overlap = overlap

        diarization_confidence = None
        if segment_start is not None and segment_end is not None and segment_end > segment_start:
            diarization_confidence = round(best_overlap / (segment_end - segment_start), 4)

        aligned_segment = {
            **segment,
            "speaker_id": best_turn.get("speaker_id") if best_turn else None,
            "speaker_name": None,
            "speaker_confidence": diarization_confidence,
            "diarization_confidence": diarization_confidence,
        }
        aligned_segments.append(aligned_segment)

    return aligned_segments


def speaker_excerpt_lines(segments: list[dict[str, object]], max_lines_per_speaker: int = 24) -> list[str]:
    grouped: dict[str, list[str]] = {}
    for segment in segments:
        speaker_id = segment.get("speaker_id")
        text = str(segment.get("text", "")).strip()
        if not speaker_id or not text:
            continue
        grouped.setdefault(str(speaker_id), [])
        if len(grouped[str(speaker_id)]) >= max_lines_per_speaker:
            continue
        start = number_value(segment.get("start")) or 0.0
        grouped[str(speaker_id)].append(f"[{format_seconds(start)}] {text}")

    lines = []
    for speaker_id in sorted(grouped):
        lines.append(f"{speaker_id}:")
        lines.extend(grouped[speaker_id])
    return lines


def parse_json_object(value: str) -> dict[str, object]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", value, re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))

    if not isinstance(parsed, dict):
        raise ValueError("LLM response must be a JSON object")
    return parsed


def resolve_speaker_names(
    segments: list[dict[str, object]],
    model: str,
    ollama_base_url: str,
) -> dict[str, dict[str, object]]:
    import requests

    speaker_ids = sorted({str(segment["speaker_id"]) for segment in segments if segment.get("speaker_id")})
    if not speaker_ids:
        return {}

    excerpts = "\n".join(speaker_excerpt_lines(segments))
    prompt = f"""
You receive a Dutch podcast transcript with anonymous speaker labels.
Identify a speaker name only when it is clearly supported by the conversation.
Do not guess. If there is insufficient evidence, use speaker_name null and confidence 0.

Speaker labels: {", ".join(speaker_ids)}

Transcript excerpts:
{excerpts}

Return only JSON in this format:
{{
  "SPEAKER_00": {{
    "speaker_name": "Bram",
    "speaker_confidence": 0.86,
    "evidence": "brief evidence from the conversation"
  }}
}}
""".strip()

    started_at = time.monotonic()
    log(f"Resolving speaker names with Ollama model '{model}'")
    response = requests.post(
        f"{ollama_base_url.rstrip('/')}/api/chat",
        json={
            "model": model,
            "stream": False,
            "format": "json",
            "messages": [
                {
                    "role": "system",
                    "content": "You are careful in speaker identification. You return strict JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
        },
        timeout=120,
    )
    response.raise_for_status()
    content = response.json()["message"]["content"]
    parsed = parse_json_object(content)
    mapping = {}
    for speaker_id in speaker_ids:
        speaker_value = parsed.get(speaker_id)
        if not isinstance(speaker_value, dict):
            mapping[speaker_id] = {
                "speaker_name": None,
                "speaker_confidence": 0.0,
                "evidence": None,
            }
            continue

        speaker_name = speaker_value.get("speaker_name")
        confidence = speaker_value.get("speaker_confidence", 0.0)
        mapping[speaker_id] = {
            "speaker_name": str(speaker_name) if speaker_name else None,
            "speaker_confidence": float(confidence) if isinstance(confidence, int | float) else 0.0,
            "evidence": speaker_value.get("evidence"),
        }

    log(f"Resolved {len(mapping)} speaker labels in {format_seconds(time.monotonic() - started_at)}")
    return mapping


def apply_speaker_mapping(
    segments: list[dict[str, object]],
    speaker_mapping: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    resolved_segments = []
    for segment in segments:
        speaker_id = segment.get("speaker_id")
        mapping = speaker_mapping.get(str(speaker_id), {}) if speaker_id else {}
        speaker_name = mapping.get("speaker_name")
        if speaker_name:
            speaker_confidence = mapping.get("speaker_confidence", segment.get("speaker_confidence"))
        else:
            speaker_confidence = segment.get("speaker_confidence")

        resolved_segments.append(
            {
                **segment,
                "speaker_name": speaker_name,
                "speaker_confidence": speaker_confidence,
            }
        )
    return resolved_segments


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_transcript_payload(
    audio_url: str,
    model_size: str,
    compute_type: str,
    device: str,
    beam_size: int,
    hotwords: str | None,
    language: str | None,
    diarization_enabled: bool,
    diarization_model: str,
    diarization_device: str,
    diarization_turns: list[dict[str, object]],
    speaker_name_resolution_enabled: bool,
    speaker_name_model: str,
    speaker_mapping: dict[str, dict[str, object]],
    segments: list[dict[str, object]],
    info: object,
) -> dict[str, object]:
    info_get = info.get if isinstance(info, dict) else lambda key, default=None: getattr(info, key, default)
    return {
        "audio_url": audio_url,
        "engine": "faster-whisper",
        "model": model_size,
        "compute_type": compute_type,
        "device": device,
        "beam_size": beam_size,
        "hotwords": hotwords,
        "language": language,
        "diarization_enabled": diarization_enabled,
        "diarization_model": diarization_model if diarization_enabled else None,
        "diarization_device": diarization_device if diarization_enabled else None,
        "diarization_turns": diarization_turns,
        "speaker_name_resolution_enabled": speaker_name_resolution_enabled,
        "speaker_name_model": speaker_name_model if speaker_name_resolution_enabled else None,
        "speaker_mapping": speaker_mapping,
        "detected_language": info_get("language"),
        "language_probability": info_get("language_probability"),
        "duration": info_get("duration"),
        "segments": segments,
    }


def write_transcript(transcript_path: Path, payload: dict[str, object]) -> None:
    started_at = time.monotonic()
    transcript_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log(f"Wrote transcript JSON to {transcript_path} in {format_seconds(time.monotonic() - started_at)}")


def process_audio_url(audio_url: str, write_files: bool = True) -> tuple[dict[str, object], Path]:
    model_size = os.getenv("TRANSCRIBE_MODEL", DEFAULT_MODEL_SIZE)
    compute_type = os.getenv("TRANSCRIBE_COMPUTE_TYPE", DEFAULT_COMPUTE_TYPE)
    device = os.getenv("TRANSCRIBE_DEVICE", DEFAULT_DEVICE)
    beam_size = int_env("TRANSCRIBE_BEAM_SIZE", DEFAULT_BEAM_SIZE)
    heartbeat_seconds = int_env("TRANSCRIBE_PROGRESS_HEARTBEAT_SECONDS", DEFAULT_PROGRESS_HEARTBEAT_SECONDS)
    hotwords = os.getenv("TRANSCRIBE_HOTWORDS", DEFAULT_HOTWORDS) or None
    language = os.getenv("TRANSCRIBE_LANGUAGE") or None
    diarization_enabled = bool_env("DIARIZATION_ENABLED", DEFAULT_DIARIZATION_ENABLED)
    diarization_model = os.getenv("DIARIZATION_MODEL", DEFAULT_DIARIZATION_MODEL)
    diarization_device = os.getenv("DIARIZATION_DEVICE", device if device != "auto" else DEFAULT_DIARIZATION_DEVICE)
    speaker_name_resolution_enabled = bool_env(
        "SPEAKER_NAME_RESOLUTION_ENABLED",
        DEFAULT_SPEAKER_NAME_RESOLUTION_ENABLED,
    )
    speaker_name_model = os.getenv("SPEAKER_NAME_MODEL", DEFAULT_SPEAKER_NAME_MODEL)
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL)
    audio_path, transcript_path = tmp_paths(audio_url)
    diarization_path, speaker_mapping_path = metadata_paths(audio_url)
    transcript_written = False
    log(
        "Starting transcription "
        f"engine='faster-whisper' model='{model_size}' device='{device}' compute_type='{compute_type}' beam_size={beam_size} "
        f"language='{language or 'auto'}' "
        f"heartbeat='{format_seconds(heartbeat_seconds) if heartbeat_seconds > 0 else 'off'}' "
        f"diarization_enabled={diarization_enabled} "
        f"speaker_name_resolution_enabled={speaker_name_resolution_enabled}"
    )

    try:
        download_audio(audio_url, audio_path)
        segments, info = transcribe_audio(
            audio_path,
            model_size,
            compute_type,
            device,
            beam_size,
            hotwords,
            heartbeat_seconds,
            language,
        )

        diarization_turns = []
        speaker_mapping = {}
        if diarization_enabled:
            diarization_turns = run_diarization(audio_path, diarization_model, diarization_device)
            if write_files:
                write_json(
                    diarization_path,
                    {
                        "audio_url": audio_url,
                        "diarization_model": diarization_model,
                        "diarization_device": diarization_device,
                        "turns": diarization_turns,
                    },
                )
                log(f"Wrote diarization JSON to {diarization_path}")
            segments = align_segments_with_speakers(segments, diarization_turns)

        if diarization_enabled and speaker_name_resolution_enabled:
            speaker_mapping = resolve_speaker_names(segments, speaker_name_model, ollama_base_url)
            if write_files:
                write_json(
                    speaker_mapping_path,
                    {
                        "audio_url": audio_url,
                        "speaker_name_model": speaker_name_model,
                        "speaker_mapping": speaker_mapping,
                    },
                )
                log(f"Wrote speaker mapping JSON to {speaker_mapping_path}")
            segments = apply_speaker_mapping(segments, speaker_mapping)

        payload = build_transcript_payload(
            audio_url,
            model_size,
            compute_type,
            device,
            beam_size,
            hotwords,
            language,
            diarization_enabled,
            diarization_model,
            diarization_device,
            diarization_turns,
            speaker_name_resolution_enabled,
            speaker_name_model,
            speaker_mapping,
            segments,
            info,
        )
        if write_files:
            write_transcript(transcript_path, payload)
        transcript_written = True
    except subprocess.CalledProcessError as error:
        print(f"Audio download failed: {error}", file=sys.stderr)
        raise
    finally:
        if transcript_written and audio_path.exists():
            audio_path.unlink()
            log(f"Removed audio file {audio_path}")

    return payload, transcript_path


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Transcribe podcast audio to /tmp JSON.")
    parser.add_argument("audio_url", help="Podcast audio URL to download and transcribe.")
    args = parser.parse_args()

    try:
        _, transcript_path = process_audio_url(args.audio_url, write_files=True)
    except subprocess.CalledProcessError as error:
        return error.returncode or 1

    print(transcript_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
