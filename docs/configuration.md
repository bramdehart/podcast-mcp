# Configuration

All configuration is read from environment variables and centralized in
`src/podcast_mcp/config.py`. Copy `.env.example` to `.env` and adjust values.

```bash
cp .env.example .env
```

## Database

| Variable       | Default | Description                                  |
| -------------- | ------- | -------------------------------------------- |
| `DATABASE_URL` | —       | Postgres DSN, e.g. `postgresql://user:pass@localhost:5432/podcast_mcp` |
| `POSTGRES_DB`  | `podcast_mcp` | Database name (used by Docker Compose)  |
| `POSTGRES_USER`| `podcast_mcp` | Database user (used by Docker Compose)  |
| `POSTGRES_PASSWORD` | `podcast_mcp` | Database password (used by Docker Compose) |

## RSS sync

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `RSS_URL` | — | Podcast RSS feed URL. |
| `SYNC_CRON` | `0 6 * * 5` | Cron expression for the scheduler. |
| `SYNC_TIMEZONE` | `Europe/Amsterdam` | Timezone for the scheduler. |
| `SYNC_MAX_EPISODES` | `10` | Max episodes per sync run. |
| `SYNC_MAX_RUNTIME_SECONDS` | `19800` | Max wall time per sync run. |

## Transcription execution

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `TRANSCRIBE_EXECUTION` | `local` | `local` (in-process worker) or `runpod`. |

## Whisper transcription

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `TRANSCRIBE_MODEL` | `medium` | faster-whisper model size. |
| `TRANSCRIBE_COMPUTE_TYPE` | `int8` | Compute type (`float16`, `int8`, ...). |
| `TRANSCRIBE_DEVICE` | `auto` | Device (`auto`, `cuda`, `cpu`). |
| `TRANSCRIBE_BEAM_SIZE` | `5` | Beam size. |
| `TRANSCRIBE_CHUNK_SECONDS` | `1800` | Split long audio into chunks of N seconds. |
| `TRANSCRIBE_LANGUAGE` | — | Language code or empty for auto-detect. |
| `TRANSCRIBE_HOTWORDS` | — | Comma-separated hotwords to bias transcription. |

## Speaker diarization

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `DIARIZATION_ENABLED` | `false` | Enable pyannote diarization. |
| `DIARIZATION_MODEL` | `pyannote/speaker-diarization-3.1` | Diarization model. |
| `DIARIZATION_DEVICE` | `auto` | Device for diarization. |
| `DIARIZATION_MIN_SPEAKERS` | `2` | Minimum expected speakers. |
| `DIARIZATION_MAX_SPEAKERS` | `4` | Maximum expected speakers. |
| `HUGGINGFACE_TOKEN` | — | Required when diarization is enabled. |
| `HF_TOKEN` | — | Alias for `HUGGINGFACE_TOKEN`. |

## Speaker name resolution

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `SPEAKER_NAME_RESOLUTION_ENABLED` | `false` | Resolve anonymous labels to names. |
| `SPEAKER_NAME_MODEL` | `gpt-5.4-mini` | OpenAI model used for resolution. |
| `OPENAI_API_KEY` | — | Required for speaker names and embeddings. |

## Embeddings

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model. |
| `EMBEDDING_DIMENSIONS` | `1536` | Embedding dimensions. |
| `EMBEDDING_BATCH_SIZE` | `64` | Batch size for embedding requests. |
| `CHUNK_MAX_CHARS` | `2000` | Max characters per transcript chunk. |
| `CHUNK_MAX_SECONDS` | `180` | Max seconds per transcript chunk. |

## RunPod

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `RUNPOD_API_KEY` | — | RunPod API key. |
| `RUNPOD_ENDPOINT_ID` | — | RunPod serverless endpoint id. |
| `RUNPOD_POLL_INTERVAL_SECONDS` | `10` | Poll interval while waiting for a job. |
| `RUNPOD_EXECUTION_TIMEOUT_MS` | `1800000` | Job execution timeout. |
| `RUNPOD_TTL_MS` | `3600000` | Job result TTL. |

## MCP server

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `MCP_TRANSPORT` | `stdio` | `stdio`, `streamable-http`, or `sse`. |
| `MCP_HOST` | `127.0.0.1` | Bind host. |
| `MCP_PORT` | `8000` | Bind port. |
| `MCP_PUBLIC_URL` | `http://localhost:8000` | Public URL used for auth metadata. |
| `MCP_BEARER_TOKEN` | — | Required for remote transports. Generate with `openssl rand -hex 32`. |
| `MCP_RATE_LIMIT_REQUESTS` | `60` | Requests per IP per window. |
| `MCP_RATE_LIMIT_WINDOW_SECONDS` | `60` | Sliding window length. |