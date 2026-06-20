# RunPod transcription worker

This setup moves the heavy audio processing to a RunPod Serverless worker:

1. Download audio in the worker to `/tmp`.
2. Transcribe with Faster Whisper.
3. Optionally run pyannote diarization.
4. Return transcript JSON to the local client.
5. Optionally run speaker-name mapping locally via Ollama.
6. The local client writes `/tmp/podcast_transcript_<hash>.json`.

## Local env

Set locally:

```env
TRANSCRIBE_EXECUTION=runpod
RUNPOD_API_KEY=...
RUNPOD_ENDPOINT_ID=...
TRANSCRIBE_MODEL=medium
TRANSCRIBE_DEVICE=cuda
TRANSCRIBE_COMPUTE_TYPE=float16
TRANSCRIBE_BEAM_SIZE=1
DIARIZATION_ENABLED=true
DIARIZATION_DEVICE=cuda
HUGGINGFACE_TOKEN=...
```

After that, the existing RSS flow stays the same:

```bash
python sync_rss.py
```

## Worker image

The GitHub Actions workflow `.github/workflows/publish-worker-image.yml` automatically builds and pushes:

```text
ghcr.io/bramdehart/podcast-rag-worker:latest
```

You can start the workflow manually from GitHub Actions, or automatically by pushing to `main`.

Then use this in RunPod:

```env
Container image=ghcr.io/bramdehart/podcast-rag-worker:latest
Template=No template
Start command=
```

You can also build and push manually:

```bash
docker build -f Dockerfile.worker -t ghcr.io/bramdehart/podcast-rag-worker:latest .
docker push ghcr.io/bramdehart/podcast-rag-worker:latest
```

After that, create a RunPod Serverless endpoint with this image.

The worker image uses a recent PyTorch/CUDA base image because RunPod Serverless GPU pools can include newer GPU architectures.
Older CUDA images can fail the RunPod fitness check with `no kernel image is available for execution on the device`.
The RunPod image pins `torchcodec` to the PyTorch-compatible version. Mismatched TorchCodec/PyTorch/CUDA builds can fail at startup with missing CUDA runtime libraries.

## Localhost callback

RunPod cannot call back to your `localhost` directly: for RunPod, `localhost` means the worker container itself.
This implementation therefore uses polling through the RunPod API. This also works while the rest of the app still runs locally.

## Ollama

If `SPEAKER_NAME_RESOLUTION_ENABLED=true`, `runpod_client.py` runs speaker-name mapping locally after RunPod completes.
This means `OLLAMA_BASE_URL=http://localhost:11434` can point to Ollama on your Mac.
