# Hetzner deployment

This server runs the database, RSS sync, transcript ingestion, embeddings, and MCP service.
GPU transcription and diarization stay on RunPod.

## Services

- `postgres`: Postgres with pgvector and persistent `postgres_data` volume.
- `app`: one-off container for manual commands such as RSS sync.
- `scheduler`: long-running container that starts `sync_rss.py` based on `SYNC_CRON`.

## Production environment

Create a server-local env file, for example `.env.production`. Do not commit it.

### Required on Hetzner

```env
POSTGRES_DB=podcast_rag
POSTGRES_USER=podcast_rag
POSTGRES_PASSWORD=<strong-postgres-password>
RSS_URL=https://example.com/feed.xml
SYNC_CRON=0 6 * * 5
SYNC_TIMEZONE=Europe/Amsterdam
SYNC_MAX_EPISODES=10
SYNC_MAX_RUNTIME_SECONDS=19800
TRANSCRIBE_EXECUTION=runpod
OPENAI_API_KEY=<openai-api-key>
EMBEDDING_MODEL=text-embedding-3-small
RUNPOD_API_KEY=<runpod-api-key>
RUNPOD_ENDPOINT_ID=<runpod-endpoint-id>
RUNPOD_POLL_INTERVAL_SECONDS=10
RUNPOD_EXECUTION_TIMEOUT_MS=1800000
RUNPOD_TTL_MS=3600000
MCP_TRANSPORT=streamable-http
MCP_BIND_ADDRESS=127.0.0.1
MCP_HOST=0.0.0.0
MCP_PORT=8000
MCP_PUBLIC_URL=https://mcp.example.com
MCP_BEARER_TOKEN=<strong-mcp-token>
MCP_RATE_LIMIT_REQUESTS=60
MCP_RATE_LIMIT_WINDOW_SECONDS=60
```

`DATABASE_URL` is optional when running through Docker Compose. Compose builds the
internal app database URL from `POSTGRES_DB`, `POSTGRES_USER`, and
`POSTGRES_PASSWORD`, using the private Docker hostname `postgres`.

### Required on RunPod worker

These values belong in the RunPod endpoint environment, not on Hetzner, unless local
transcription is explicitly enabled.

```env
TRANSCRIBE_MODEL=large-v3
TRANSCRIBE_DEVICE=cuda
TRANSCRIBE_COMPUTE_TYPE=float16
TRANSCRIBE_BEAM_SIZE=5
TRANSCRIBE_CHUNK_SECONDS=1800
TRANSCRIBE_LANGUAGE=nl
TRANSCRIBE_HOTWORDS=Anthropic, Claude, ChatGPT, OpenAI, Gemini, Grok, OpenRouter, OpenClaw, Clawbot, Mistral, Ollama, HuggingFace
DIARIZATION_ENABLED=true
DIARIZATION_MODEL=pyannote/speaker-diarization-3.1
DIARIZATION_DEVICE=cuda
DIARIZATION_MIN_SPEAKERS=2
DIARIZATION_MAX_SPEAKERS=4
HUGGINGFACE_TOKEN=<huggingface-token>
SPEAKER_NAME_RESOLUTION_ENABLED=true
SPEAKER_NAME_MODEL=gpt-5.4
OPENAI_API_KEY=<openai-api-key>
```

## Commands

Start the database:

```bash
APP_ENV_FILE=.env.production docker compose up -d postgres
```

Run one manual RSS sync:

```bash
APP_ENV_FILE=.env.production docker compose --profile tools run --rm app
```

Resolve missing speaker names for already-ingested episodes without rerunning
RunPod transcription or embeddings:

```bash
APP_ENV_FILE=.env.production docker compose --profile tools run --rm app python resolve_speaker_names_db.py
```

Start the scheduler:

```bash
APP_ENV_FILE=.env.production docker compose --profile scheduler up -d scheduler
```

View logs:

```bash
docker compose logs -f postgres
docker compose --profile scheduler logs -f scheduler
```

## First smoke test

1. Start Postgres.
2. Run one manual sync with `SYNC_MAX_EPISODES=1`.
3. Confirm an episode was stored.
4. Start the scheduler only after the manual sync succeeds.
5. Add the public MCP service only after auth and rate limiting are enabled.
