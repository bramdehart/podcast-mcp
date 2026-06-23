#!/usr/bin/env python3
import os
from contextlib import contextmanager
from typing import Iterator

import runpod

from transcribe import process_audio_url


ENV_KEYS = {
    "TRANSCRIBE_MODEL",
    "TRANSCRIBE_COMPUTE_TYPE",
    "TRANSCRIBE_DEVICE",
    "TRANSCRIBE_BEAM_SIZE",
    "TRANSCRIBE_CONDITION_ON_PREVIOUS_TEXT",
    "TRANSCRIBE_CHUNK_SECONDS",
    "TRANSCRIBE_PROGRESS_HEARTBEAT_SECONDS",
    "TRANSCRIBE_LANGUAGE",
    "TRANSCRIBE_HOTWORDS",
    "DIARIZATION_ENABLED",
    "DIARIZATION_MODEL",
    "DIARIZATION_DEVICE",
    "DIARIZATION_MIN_SPEAKERS",
    "DIARIZATION_MAX_SPEAKERS",
    "HUGGINGFACE_TOKEN",
    "HF_TOKEN",
    "SPEAKER_NAME_RESOLUTION_ENABLED",
    "SPEAKER_NAME_MODEL",
    "OLLAMA_BASE_URL",
}


@contextmanager
def job_environment(values: dict[str, object]) -> Iterator[None]:
    previous_values = {}
    for key, value in values.items():
        if key not in ENV_KEYS or value is None:
            continue
        previous_values[key] = os.environ.get(key)
        os.environ[key] = str(value)

    try:
        yield
    finally:
        for key, previous_value in previous_values.items():
            if previous_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous_value


def handler(job: dict[str, object]) -> dict[str, object]:
    job_input = job.get("input") if isinstance(job.get("input"), dict) else {}
    audio_url = job_input.get("audio_url") if isinstance(job_input, dict) else None
    if not audio_url:
        raise ValueError("RunPod job input must include audio_url")

    env = job_input.get("env") if isinstance(job_input.get("env"), dict) else {}
    with job_environment(env):
        transcript, _ = process_audio_url(str(audio_url), write_files=False)

    return {"transcript": transcript}


runpod.serverless.start({"handler": handler})
