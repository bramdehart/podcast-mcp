#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

from transcribe import (
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_SPEAKER_NAME_MODEL,
    DEFAULT_SPEAKER_NAME_RESOLUTION_ENABLED,
    apply_speaker_mapping,
    bool_env,
    format_seconds,
    metadata_paths,
    resolve_speaker_names,
    tmp_paths,
    write_json,
)


RUNPOD_API_BASE_URL = "https://api.runpod.ai/v2"
DEFAULT_POLL_INTERVAL_SECONDS = 10
DEFAULT_EXECUTION_TIMEOUT_MS = 6 * 60 * 60 * 1000
DEFAULT_TTL_MS = 24 * 60 * 60 * 1000
TERMINAL_STATUSES = {"COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"}

WORKER_ENV_KEYS = [
    "TRANSCRIBE_MODEL",
    "TRANSCRIBE_COMPUTE_TYPE",
    "TRANSCRIBE_DEVICE",
    "TRANSCRIBE_BEAM_SIZE",
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
]


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def runpod_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def worker_env() -> dict[str, str]:
    values = {key: value for key in WORKER_ENV_KEYS if (value := os.getenv(key))}
    values["SPEAKER_NAME_RESOLUTION_ENABLED"] = "false"
    return values


def endpoint_url(endpoint_id: str, action: str) -> str:
    return f"{RUNPOD_API_BASE_URL}/{endpoint_id}/{action}"


def submit_job(api_key: str, endpoint_id: str, audio_url: str) -> str:
    payload = {
        "input": {
            "audio_url": audio_url,
            "env": worker_env(),
        },
        "policy": {
            "executionTimeout": int_env("RUNPOD_EXECUTION_TIMEOUT_MS", DEFAULT_EXECUTION_TIMEOUT_MS),
            "ttl": int_env("RUNPOD_TTL_MS", DEFAULT_TTL_MS),
        },
    }
    response = requests.post(
        endpoint_url(endpoint_id, "run"),
        headers=runpod_headers(api_key),
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    response_payload = response.json()
    job_id = response_payload.get("id")
    if not job_id:
        raise RuntimeError(f"RunPod did not return a job id: {response_payload}")
    return str(job_id)


def poll_job(api_key: str, endpoint_id: str, job_id: str) -> dict[str, object]:
    poll_interval = int_env("RUNPOD_POLL_INTERVAL_SECONDS", DEFAULT_POLL_INTERVAL_SECONDS)
    started_at = time.monotonic()

    while True:
        response = requests.get(
            endpoint_url(endpoint_id, f"status/{job_id}"),
            headers=runpod_headers(api_key),
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        status = str(payload.get("status", "UNKNOWN"))
        log(f"RunPod job {job_id} status={status} after {format_seconds(time.monotonic() - started_at)}")

        if status in TERMINAL_STATUSES:
            return payload

        time.sleep(poll_interval)


def extract_transcript(status_payload: dict[str, object]) -> dict[str, object]:
    status = status_payload.get("status")
    if status != "COMPLETED":
        raise RuntimeError(f"RunPod job ended with status={status}: {status_payload}")

    output = status_payload.get("output")
    if isinstance(output, dict) and isinstance(output.get("transcript"), dict):
        return output["transcript"]
    if isinstance(output, dict):
        return output

    raise RuntimeError(f"RunPod completed without transcript output: {status_payload}")


def write_transcript(audio_url: str, transcript: dict[str, object]) -> Path:
    _, transcript_path = tmp_paths(audio_url)
    transcript_path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")
    return transcript_path


def resolve_speaker_names_locally(audio_url: str, transcript: dict[str, object]) -> dict[str, object]:
    if not transcript.get("diarization_enabled"):
        return transcript
    if not bool_env("SPEAKER_NAME_RESOLUTION_ENABLED", DEFAULT_SPEAKER_NAME_RESOLUTION_ENABLED):
        return transcript

    segments = transcript.get("segments")
    if not isinstance(segments, list):
        return transcript

    speaker_name_model = os.getenv("SPEAKER_NAME_MODEL", DEFAULT_SPEAKER_NAME_MODEL)
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL)
    try:
        speaker_mapping = resolve_speaker_names(segments, speaker_name_model, ollama_base_url)
    except Exception as error:
        log(f"Speaker name resolution skipped: {error}")
        transcript["speaker_name_resolution_enabled"] = False
        transcript["speaker_name_resolution_error"] = str(error)
        return transcript

    transcript["speaker_name_resolution_enabled"] = True
    transcript["speaker_name_model"] = speaker_name_model
    transcript["speaker_mapping"] = speaker_mapping
    transcript["segments"] = apply_speaker_mapping(segments, speaker_mapping)

    _, speaker_mapping_path = metadata_paths(audio_url)
    write_json(
        speaker_mapping_path,
        {
            "audio_url": audio_url,
            "speaker_name_model": speaker_name_model,
            "speaker_mapping": speaker_mapping,
        },
    )
    log(f"Wrote local speaker mapping JSON to {speaker_mapping_path}")
    return transcript


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Submit podcast transcription to a RunPod serverless endpoint.")
    parser.add_argument("audio_url", help="Podcast audio URL to transcribe on RunPod.")
    parser.add_argument("--job-id", help="Existing RunPod job id to poll/recover instead of submitting a new job.")
    args = parser.parse_args()

    api_key = os.getenv("RUNPOD_API_KEY")
    endpoint_id = os.getenv("RUNPOD_ENDPOINT_ID")
    if not api_key:
        print("RUNPOD_API_KEY missing. Add it to .env or export it.", file=sys.stderr)
        return 1
    if not endpoint_id:
        print("RUNPOD_ENDPOINT_ID missing. Add it to .env or export it.", file=sys.stderr)
        return 1

    if args.job_id:
        job_id = args.job_id
        log(f"Recovering RunPod job {job_id}")
    else:
        job_id = submit_job(api_key, endpoint_id, args.audio_url)
        log(f"Submitted RunPod job {job_id}")

    status_payload = poll_job(api_key, endpoint_id, job_id)
    transcript = extract_transcript(status_payload)
    transcript = resolve_speaker_names_locally(args.audio_url, transcript)
    transcript_path = write_transcript(args.audio_url, transcript)
    log(f"Wrote RunPod transcript JSON to {transcript_path}")
    print(transcript_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
