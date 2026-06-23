#!/usr/bin/env python3
import argparse
from collections import namedtuple
import gc
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import warnings
import wave
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
warnings.filterwarnings(
    "ignore",
    message="The 'backend' parameter is not used by TorchCodec AudioDecoder.*",
    category=UserWarning,
)

TMP_DIR = Path("/tmp")
USER_AGENT = "AppleCoreMedia"
DEFAULT_MODEL_SIZE = "medium"
DEFAULT_COMPUTE_TYPE = "int8"
DEFAULT_DEVICE = "auto"
DEFAULT_BEAM_SIZE = 5
CONDITION_ON_PREVIOUS_TEXT = False
VAD_FILTER = True
NO_SPEECH_THRESHOLD = 0.5
DEFAULT_CHUNK_SECONDS = 1800
DEFAULT_HOTWORDS = ""
DEFAULT_DIARIZATION_ENABLED = False
DEFAULT_DIARIZATION_MODEL = "pyannote/speaker-diarization-3.1"
DEFAULT_DIARIZATION_DEVICE = "auto"
DEFAULT_DIARIZATION_MIN_SPEAKERS = 2
DEFAULT_DIARIZATION_MAX_SPEAKERS = 4
DEFAULT_SPEAKER_NAME_RESOLUTION_ENABLED = False
DEFAULT_SPEAKER_NAME_MODEL = "gpt-5.4"
PROGRESS_HEARTBEAT_SECONDS = 60
PROGRESS_LOG_INTERVAL_SECONDS = 300
MAX_EPISODE_DESCRIPTION_PROMPT_CHARS = 4000


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


def optional_int_env(name: str, default: int | None = None) -> int | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def cleanup_gpu_memory(label: str) -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
            log(f"Cleaned CUDA memory after {label}")
    except Exception as error:
        log(f"CUDA cleanup skipped after {label}: {error}")


def prompt_description(value: str | None) -> str:
    if not value:
        return "none provided"
    normalized = re.sub(r"\s+", " ", value).strip()
    if len(normalized) <= MAX_EPISODE_DESCRIPTION_PROMPT_CHARS:
        return normalized
    return normalized[:MAX_EPISODE_DESCRIPTION_PROMPT_CHARS].rstrip() + "..."


def resolve_torch_device(device: str) -> str:
    normalized_device = device.strip().lower()
    if normalized_device != "auto":
        return normalized_device

    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


def log_acceleration_status(transcribe_device: str, diarization_device: str) -> None:
    wants_cuda = "cuda" in {transcribe_device.strip().lower(), diarization_device.strip().lower()}
    log(
        "Acceleration config "
        f"transcribe_device='{transcribe_device}' diarization_device='{diarization_device}' "
        f"CUDA_VISIBLE_DEVICES='{os.getenv('CUDA_VISIBLE_DEVICES', '')}'"
    )
    if not wants_cuda:
        return

    try:
        import torch

        log(
            "Torch CUDA status "
            f"torch='{torch.__version__}' available={torch.cuda.is_available()} "
            f"device_count={torch.cuda.device_count()}"
        )
        for device_index in range(torch.cuda.device_count()):
            log(f"Torch CUDA device {device_index}: {torch.cuda.get_device_name(device_index)}")
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested, but torch.cuda.is_available() is false")
    except Exception as error:
        log(f"Torch CUDA preflight failed: {error}")
        raise

    try:
        import ctranslate2

        cuda_device_count = getattr(ctranslate2, "get_cuda_device_count", lambda: "unknown")()
        supported_compute_types = ctranslate2.get_supported_compute_types("cuda")
        log(
            "CTranslate2 CUDA status "
            f"ctranslate2='{ctranslate2.__version__}' cuda_device_count={cuda_device_count} "
            f"supported_compute_types={sorted(supported_compute_types)}"
        )
        if cuda_device_count == 0:
            raise RuntimeError("CUDA was requested, but CTranslate2 sees 0 CUDA devices")
    except Exception as error:
        log(f"CTranslate2 CUDA preflight failed: {error}")
        raise

    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        log(f"nvidia-smi: {result.stdout.strip()}")
    except Exception as error:
        log(f"nvidia-smi unavailable: {error}")


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


def wav_path_for_audio(audio_url: str) -> Path:
    audio_hash = hashlib.sha256(audio_url.encode("utf-8")).hexdigest()[:16]
    return TMP_DIR / f"podcast_audio_{audio_hash}.wav"


def chunk_wav_path_for_audio(audio_url: str, chunk_index: int) -> Path:
    audio_hash = hashlib.sha256(audio_url.encode("utf-8")).hexdigest()[:16]
    return TMP_DIR / f"podcast_audio_{audio_hash}_chunk_{chunk_index:03d}.wav"


def metadata_paths(audio_url: str) -> tuple[Path, Path]:
    audio_hash = hashlib.sha256(audio_url.encode("utf-8")).hexdigest()[:16]
    diarization_path = TMP_DIR / f"podcast_diarization_{audio_hash}.json"
    speaker_mapping_path = TMP_DIR / f"podcast_speaker_mapping_{audio_hash}.json"
    return diarization_path, speaker_mapping_path


def download_audio(audio_url: str, audio_path: Path) -> float:
    started_at = time.monotonic()
    log(f"Downloading audio to {audio_path}")
    subprocess.run(
        ["curl", "-fsSL", "-A", USER_AGENT, audio_url, "-o", str(audio_path)],
        check=True,
    )
    elapsed_seconds = time.monotonic() - started_at
    log(f"Downloaded {audio_path.stat().st_size / 1024 / 1024:.1f} MB in {format_seconds(elapsed_seconds)}")
    return elapsed_seconds


def convert_audio_to_wav(audio_path: Path, wav_path: Path) -> float:
    started_at = time.monotonic()
    log(f"Converting audio to 16kHz mono WAV at {wav_path}")
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(audio_path),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-vn",
            str(wav_path),
        ],
        check=True,
    )
    elapsed_seconds = time.monotonic() - started_at
    log(
        f"Converted WAV {wav_path.stat().st_size / 1024 / 1024:.1f} MB "
        f"in {format_seconds(elapsed_seconds)}"
    )
    return elapsed_seconds


def wav_duration_seconds(wav_path: Path) -> float:
    with wave.open(str(wav_path), "rb") as wav_file:
        frame_count = wav_file.getnframes()
        frame_rate = wav_file.getframerate()
        return frame_count / frame_rate


def split_wav_chunk(source_wav_path: Path, chunk_wav_path: Path, offset_seconds: float, duration_seconds: float) -> float:
    started_at = time.monotonic()
    log(
        f"Creating WAV chunk {chunk_wav_path.name} "
        f"from {format_seconds(offset_seconds)} for {format_seconds(duration_seconds)}"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source_wav_path),
            "-ss",
            str(offset_seconds),
            "-t",
            str(duration_seconds),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(chunk_wav_path),
        ],
        check=True,
    )
    elapsed_seconds = time.monotonic() - started_at
    log(
        f"Created WAV chunk {chunk_wav_path.name} "
        f"{chunk_wav_path.stat().st_size / 1024 / 1024:.1f} MB in {format_seconds(elapsed_seconds)}"
    )
    return elapsed_seconds


def offset_segments(segments: list[dict[str, object]], offset_seconds: float) -> list[dict[str, object]]:
    offset_result = []
    for segment in segments:
        updated_segment = dict(segment)
        start = number_value(segment.get("start"))
        end = number_value(segment.get("end"))
        if start is not None:
            updated_segment["start"] = start + offset_seconds
        if end is not None:
            updated_segment["end"] = end + offset_seconds
        offset_result.append(updated_segment)
    return offset_result


def offset_diarization_turns(
    turns: list[dict[str, object]],
    offset_seconds: float,
    chunk_index: int,
) -> list[dict[str, object]]:
    offset_result = []
    for turn in turns:
        updated_turn = dict(turn)
        start = number_value(turn.get("start"))
        end = number_value(turn.get("end"))
        speaker_id = turn.get("speaker_id")
        if start is not None:
            updated_turn["start"] = start + offset_seconds
        if end is not None:
            updated_turn["end"] = end + offset_seconds
        if speaker_id:
            updated_turn["speaker_id"] = f"CHUNK_{chunk_index:03d}_{speaker_id}"
        offset_result.append(updated_turn)
    return offset_result


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
    language: str | None,
) -> tuple[list[dict[str, object]], object]:
    from faster_whisper import WhisperModel

    started_at = time.monotonic()
    cleanup_gpu_memory("before Whisper load")
    log(f"Loading Whisper model '{model_size}' with device='{device}' compute_type='{compute_type}'")
    model = None
    stop_event = threading.Event()
    heartbeat_thread = None
    try:
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        log(f"Model loaded in {format_seconds(time.monotonic() - started_at)}")

        started_at = time.monotonic()
        log(
            f"Transcribing with language='{language or 'auto'}' and beam_size={beam_size} "
            f"condition_on_previous_text={CONDITION_ON_PREVIOUS_TEXT} "
            f"vad_filter={VAD_FILTER} no_speech_threshold={NO_SPEECH_THRESHOLD} "
            f"hotwords='{hotwords or ''}'"
        )
        stop_event, heartbeat_thread = start_heartbeat("Transcription", PROGRESS_HEARTBEAT_SECONDS)
        segments, info = model.transcribe(
            str(audio_path),
            language=language,
            beam_size=beam_size,
            condition_on_previous_text=CONDITION_ON_PREVIOUS_TEXT,
            vad_filter=VAD_FILTER,
            no_speech_threshold=NO_SPEECH_THRESHOLD,
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
        if model is not None:
            del model
        cleanup_gpu_memory("Whisper transcription")

    log(f"Transcribed {len(transcript_segments)} segments in {format_seconds(time.monotonic() - started_at)}")

    return transcript_segments, info


def transcribe_audio(
    audio_path: Path,
    model_size: str,
    compute_type: str,
    device: str,
    beam_size: int,
    hotwords: str | None,
    language: str | None,
) -> tuple[list[dict[str, object]], object]:
    return transcribe_with_faster_whisper(
        audio_path,
        model_size,
        compute_type,
        device,
        beam_size,
        hotwords,
        language,
    )


def run_diarization(
    audio_path: Path,
    diarization_model: str,
    diarization_device: str,
    min_speakers: int | None,
    max_speakers: int | None,
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
    waveform_started_at = time.monotonic()
    waveform_data, sample_rate = soundfile.read(str(audio_path), dtype="float32", always_2d=True)
    waveform = torch.as_tensor(waveform_data.T.copy(), dtype=torch.float32).contiguous()
    log(
        f"Loaded diarization waveform from WAV in {format_seconds(time.monotonic() - waveform_started_at)} "
        f"shape={tuple(waveform.shape)} sample_rate={sample_rate}"
    )
    if len(waveform.shape) != 2 or waveform.shape[1] == 0 or waveform.shape[0] > waveform.shape[1]:
        log(f"Skipping speaker diarization for invalid waveform shape={tuple(waveform.shape)}")
        del pipeline
        del waveform
        cleanup_gpu_memory("speaker diarization")
        return []

    diarization_options = {}
    if min_speakers is not None:
        diarization_options["min_speakers"] = min_speakers
    if max_speakers is not None:
        diarization_options["max_speakers"] = max_speakers
    log(f"Running pyannote with options={diarization_options}")
    diarization = pipeline({"waveform": waveform, "sample_rate": sample_rate}, **diarization_options)
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
    del pipeline
    del waveform
    cleanup_gpu_memory("speaker diarization")
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


def chronological_excerpt_lines(segments: list[dict[str, object]], max_lines: int = 160) -> list[str]:
    lines = []
    for segment in segments:
        speaker_id = segment.get("speaker_id")
        text = str(segment.get("text", "")).strip()
        if not speaker_id or not text:
            continue
        start = number_value(segment.get("start")) or 0.0
        lines.append(f"[{format_seconds(start)}] {speaker_id}: {text}")
        if len(lines) >= max_lines:
            break
    return lines


def speaker_excerpt_lines(segments: list[dict[str, object]], max_lines_per_speaker: int = 40) -> list[str]:
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
    episode_description: str | None = None,
    podcast_description: str | None = None,
) -> dict[str, dict[str, object]]:
    import requests

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required when SPEAKER_NAME_RESOLUTION_ENABLED=true")

    speaker_ids = sorted({str(segment["speaker_id"]) for segment in segments if segment.get("speaker_id")})
    if not speaker_ids:
        return {}

    chronological_excerpts = "\n".join(chronological_excerpt_lines(segments))
    speaker_excerpts = "\n".join(speaker_excerpt_lines(segments))
    podcast_description_text = prompt_description(podcast_description)
    episode_description_text = prompt_description(episode_description)
    prompt = f"""
You receive a podcast transcript with anonymous speaker labels.
Identify a speaker name only when it is clearly supported by the conversation.
Reason from natural language, not from exact phrase matching. The transcript may contain ASR misspellings.
Use chronological context to interpret self-introductions, host introductions, guests being introduced,
direct address, and speaker turns. If a name is clearly stated but possibly misspelled by ASR,
and podcast or episode metadata contains the canonical spelling for the same person,
use the metadata spelling as speaker_name and mention the transcript spelling in evidence.
If no matching metadata spelling exists, return the name as it appears in the transcript
and mention uncertainty in evidence.
Do not invent names that are not supported by the transcript. If there is insufficient evidence,
use speaker_name null and confidence 0.

Speaker labels: {", ".join(speaker_ids)}

Podcast channel description:
{podcast_description_text}

Podcast episode description:
{episode_description_text}

Chronological transcript excerpt:
{chronological_excerpts}

Grouped speaker excerpts:
{speaker_excerpts}

Return only JSON in this format:
{{
  "<speaker_id>": {{
    "speaker_name": "Name or null",
    "speaker_confidence": 0.86,
    "evidence": "brief evidence from the transcript"
  }}
}}
""".strip()

    started_at = time.monotonic()
    log(f"Resolving speaker names with OpenAI model '{model}'")
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "input": [
                {
                    "role": "system",
                    "content": "You are careful in speaker identification. You return strict JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            "text": {"format": {"type": "json_object"}},
        },
        timeout=120,
    )
    response.raise_for_status()
    response_payload = response.json()
    content = response_payload.get("output_text")
    if not content:
        output_items = response_payload.get("output", [])
        content_parts = []
        for item in output_items:
            for part in item.get("content", []) if isinstance(item, dict) else []:
                if isinstance(part, dict) and part.get("type") in {"output_text", "text"}:
                    content_parts.append(str(part.get("text", "")))
        content = "".join(content_parts)
    if not content:
        raise ValueError("OpenAI response did not include output text")

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
    podcast_description: str | None,
    episode_description: str | None,
    model_size: str,
    compute_type: str,
    device: str,
    beam_size: int,
    chunk_seconds: int,
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
    processing: dict[str, float],
) -> dict[str, object]:
    info_get = info.get if isinstance(info, dict) else lambda key, default=None: getattr(info, key, default)
    return {
        "audio_url": audio_url,
        "podcast_description": podcast_description,
        "episode_description": episode_description,
        "engine": "faster-whisper",
        "model": model_size,
        "compute_type": compute_type,
        "device": device,
        "beam_size": beam_size,
        "condition_on_previous_text": CONDITION_ON_PREVIOUS_TEXT,
        "vad_filter": VAD_FILTER,
        "no_speech_threshold": NO_SPEECH_THRESHOLD,
        "chunk_seconds": chunk_seconds,
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
        "processing": processing,
        "segments": segments,
    }


def write_transcript(transcript_path: Path, payload: dict[str, object]) -> None:
    started_at = time.monotonic()
    transcript_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log(f"Wrote transcript JSON to {transcript_path} in {format_seconds(time.monotonic() - started_at)}")


def process_audio_url(
    audio_url: str,
    write_files: bool = True,
    episode_description: str | None = None,
    podcast_description: str | None = None,
) -> tuple[dict[str, object], Path]:
    total_started_at = time.monotonic()
    model_size = os.getenv("TRANSCRIBE_MODEL", DEFAULT_MODEL_SIZE)
    compute_type = os.getenv("TRANSCRIBE_COMPUTE_TYPE", DEFAULT_COMPUTE_TYPE)
    device = os.getenv("TRANSCRIBE_DEVICE", DEFAULT_DEVICE)
    beam_size = int_env("TRANSCRIBE_BEAM_SIZE", DEFAULT_BEAM_SIZE)
    chunk_seconds = int_env("TRANSCRIBE_CHUNK_SECONDS", DEFAULT_CHUNK_SECONDS)
    hotwords = os.getenv("TRANSCRIBE_HOTWORDS", DEFAULT_HOTWORDS) or None
    language = os.getenv("TRANSCRIBE_LANGUAGE") or None
    diarization_enabled = bool_env("DIARIZATION_ENABLED", DEFAULT_DIARIZATION_ENABLED)
    diarization_model = os.getenv("DIARIZATION_MODEL", DEFAULT_DIARIZATION_MODEL)
    diarization_device = os.getenv("DIARIZATION_DEVICE", device if device != "auto" else DEFAULT_DIARIZATION_DEVICE)
    diarization_min_speakers = optional_int_env("DIARIZATION_MIN_SPEAKERS", DEFAULT_DIARIZATION_MIN_SPEAKERS)
    diarization_max_speakers = optional_int_env("DIARIZATION_MAX_SPEAKERS", DEFAULT_DIARIZATION_MAX_SPEAKERS)
    speaker_name_resolution_enabled = bool_env(
        "SPEAKER_NAME_RESOLUTION_ENABLED",
        DEFAULT_SPEAKER_NAME_RESOLUTION_ENABLED,
    )
    speaker_name_model = os.getenv("SPEAKER_NAME_MODEL", DEFAULT_SPEAKER_NAME_MODEL)
    audio_path, transcript_path = tmp_paths(audio_url)
    wav_path = wav_path_for_audio(audio_url)
    diarization_path, speaker_mapping_path = metadata_paths(audio_url)
    transcript_written = False
    log(
        "Starting transcription "
        f"engine='faster-whisper' model='{model_size}' device='{device}' compute_type='{compute_type}' beam_size={beam_size} "
        f"condition_on_previous_text={CONDITION_ON_PREVIOUS_TEXT} "
        f"vad_filter={VAD_FILTER} no_speech_threshold={NO_SPEECH_THRESHOLD} "
        f"chunk_seconds={chunk_seconds} "
        f"language='{language or 'auto'}' "
        f"heartbeat='{format_seconds(PROGRESS_HEARTBEAT_SECONDS) if PROGRESS_HEARTBEAT_SECONDS > 0 else 'off'}' "
        f"diarization_enabled={diarization_enabled} "
        f"diarization_min_speakers={diarization_min_speakers} "
        f"diarization_max_speakers={diarization_max_speakers} "
        f"speaker_name_resolution_enabled={speaker_name_resolution_enabled}"
    )
    log_acceleration_status(device, diarization_device)
    chunk_wav_paths: list[Path] = []

    try:
        processing: dict[str, float] = {}
        processing["download_seconds"] = round(download_audio(audio_url, audio_path), 3)
        processing["audio_conversion_seconds"] = round(convert_audio_to_wav(audio_path, wav_path), 3)
        audio_duration_seconds = wav_duration_seconds(wav_path)
        processing["audio_duration_seconds"] = round(audio_duration_seconds, 3)
        diarization_turns = []
        speaker_mapping = {}
        if chunk_seconds > 0 and audio_duration_seconds > chunk_seconds:
            log(
                f"Processing WAV in chunks of {format_seconds(chunk_seconds)} "
                f"for total duration {format_seconds(audio_duration_seconds)}"
            )
            segments = []
            first_info = None
            chunk_index = 0
            offset_seconds = 0.0
            processing["chunk_count"] = 0
            processing["chunk_creation_seconds"] = 0.0
            processing["transcription_seconds"] = 0.0
            if diarization_enabled:
                processing["diarization_seconds"] = 0.0

            while offset_seconds < audio_duration_seconds:
                chunk_duration_seconds = min(chunk_seconds, audio_duration_seconds - offset_seconds)
                chunk_wav_path = chunk_wav_path_for_audio(audio_url, chunk_index)
                chunk_wav_paths.append(chunk_wav_path)
                processing["chunk_creation_seconds"] = round(
                    processing["chunk_creation_seconds"]
                    + split_wav_chunk(wav_path, chunk_wav_path, offset_seconds, chunk_duration_seconds),
                    3,
                )
                log(
                    f"Processing chunk {chunk_index + 1} "
                    f"offset={format_seconds(offset_seconds)} "
                    f"duration={format_seconds(chunk_duration_seconds)}"
                )

                transcription_started_at = time.monotonic()
                chunk_segments, chunk_info = transcribe_audio(
                    chunk_wav_path,
                    model_size,
                    compute_type,
                    device,
                    beam_size,
                    hotwords,
                    language,
                )
                processing["transcription_seconds"] = round(
                    processing["transcription_seconds"] + time.monotonic() - transcription_started_at,
                    3,
                )
                if first_info is None:
                    first_info = chunk_info
                segments.extend(offset_segments(chunk_segments, offset_seconds))

                if diarization_enabled:
                    diarization_started_at = time.monotonic()
                    chunk_turns = run_diarization(
                        chunk_wav_path,
                        diarization_model,
                        diarization_device,
                        diarization_min_speakers,
                        diarization_max_speakers,
                    )
                    processing["diarization_seconds"] = round(
                        processing["diarization_seconds"] + time.monotonic() - diarization_started_at,
                        3,
                    )
                    diarization_turns.extend(offset_diarization_turns(chunk_turns, offset_seconds, chunk_index))

                if chunk_wav_path.exists():
                    chunk_wav_path.unlink()
                    log(f"Removed WAV chunk {chunk_wav_path}")

                processing["chunk_count"] += 1
                chunk_index += 1
                offset_seconds += chunk_duration_seconds

            info_get = (
                first_info.get
                if isinstance(first_info, dict)
                else lambda key, default=None: getattr(first_info, key, default)
            )
            info = {
                "language": info_get("language") if first_info is not None else language,
                "language_probability": info_get("language_probability") if first_info is not None else None,
                "duration": audio_duration_seconds,
            }
            if diarization_enabled:
                segments = align_segments_with_speakers(segments, diarization_turns)
        else:
            transcription_started_at = time.monotonic()
            segments, info = transcribe_audio(
                wav_path,
                model_size,
                compute_type,
                device,
                beam_size,
                hotwords,
                language,
            )
            processing["transcription_seconds"] = round(time.monotonic() - transcription_started_at, 3)

            if diarization_enabled:
                diarization_started_at = time.monotonic()
                diarization_turns = run_diarization(
                    wav_path,
                    diarization_model,
                    diarization_device,
                    diarization_min_speakers,
                    diarization_max_speakers,
                )
                processing["diarization_seconds"] = round(time.monotonic() - diarization_started_at, 3)
                segments = align_segments_with_speakers(segments, diarization_turns)

        speaker_mapping = {}
        if diarization_enabled:
            if write_files:
                write_json(
                    diarization_path,
                    {
                        "audio_url": audio_url,
                        "diarization_model": diarization_model,
                        "diarization_device": diarization_device,
                        "min_speakers": diarization_min_speakers,
                        "max_speakers": diarization_max_speakers,
                        "chunk_seconds": chunk_seconds,
                        "turns": diarization_turns,
                    },
                )
                log(f"Wrote diarization JSON to {diarization_path}")

        if diarization_enabled and speaker_name_resolution_enabled:
            speaker_mapping_started_at = time.monotonic()
            speaker_mapping = resolve_speaker_names(
                segments,
                speaker_name_model,
                episode_description,
                podcast_description,
            )
            processing["speaker_name_resolution_seconds"] = round(time.monotonic() - speaker_mapping_started_at, 3)
            if write_files:
                write_json(
                    speaker_mapping_path,
                    {
                        "audio_url": audio_url,
                        "podcast_description": podcast_description,
                        "episode_description": episode_description,
                        "speaker_name_model": speaker_name_model,
                        "speaker_mapping": speaker_mapping,
                    },
                )
                log(f"Wrote speaker mapping JSON to {speaker_mapping_path}")
            segments = apply_speaker_mapping(segments, speaker_mapping)

        payload = build_transcript_payload(
            audio_url,
            podcast_description,
            episode_description,
            model_size,
            compute_type,
            device,
            beam_size,
            chunk_seconds,
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
            {**processing, "total_seconds": round(time.monotonic() - total_started_at, 3)},
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
        if transcript_written and wav_path.exists():
            wav_path.unlink()
            log(f"Removed WAV file {wav_path}")
        for chunk_wav_path in chunk_wav_paths:
            if chunk_wav_path.exists():
                chunk_wav_path.unlink()
                log(f"Removed WAV chunk {chunk_wav_path}")
        cleanup_gpu_memory("transcription job")

    return payload, transcript_path


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Transcribe podcast audio to /tmp JSON.")
    parser.add_argument("audio_url", help="Podcast audio URL to download and transcribe.")
    parser.add_argument("--podcast-description", help="Podcast channel description used as speaker-name context.")
    parser.add_argument("--episode-description", help="Podcast episode description used as speaker-name context.")
    args = parser.parse_args()

    try:
        _, transcript_path = process_audio_url(
            args.audio_url,
            write_files=True,
            episode_description=args.episode_description,
            podcast_description=args.podcast_description,
        )
    except subprocess.CalledProcessError as error:
        return error.returncode or 1

    print(transcript_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
