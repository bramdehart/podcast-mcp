# Project Context

## Project identity

Short description:

> Speaker-aware MCP server for searchable podcast transcripts.

## What this project does

The system:

1. Reads a podcast RSS feed.
2. Detects episodes that are not yet indexed.
3. Sends each new episode audio URL to a RunPod GPU worker.
4. Transcribes audio with Whisper/faster-whisper.
5. Performs speaker diarization with pyannote.
6. Resolves anonymous speaker labels to names using OpenAI.
7. Chunks transcript segments.
8. Creates OpenAI embeddings for chunks.
9. Stores episodes, speakers, segments, chunks, and vectors in Postgres/pgvector.
10. Exposes read-only search/retrieval tools through MCP.

The source podcast used during development is AI Report, but the code should stay generic where practical.

## High-level architecture

```text
RSS feed
  -> Hetzner scheduler/app container
  -> RunPod worker for audio transcription + diarization
  -> Hetzner speaker-name resolution
  -> Hetzner ingest + OpenAI embeddings
  -> Postgres + pgvector
  -> MCP HTTP service behind Caddy
  -> Claude/Cursor/other MCP clients
```

Current deployment split:

- Hetzner VPS:
  - Postgres with pgvector
  - RSS scheduler
  - RunPod client/orchestrator
  - speaker-name resolution
  - transcript ingest
  - embeddings
  - MCP service
  - Caddy reverse proxy
- RunPod:
  - audio download
  - faster-whisper transcription
  - pyannote diarization
  - returns transcript JSON to Hetzner

## Important files

- `src/podcast_mcp/ingest/rss.py` — reads RSS, finds new episodes, calls transcription, ingests result.
- `src/podcast_mcp/ingest/scheduler.py` — cron-like scheduler around `podcast_mcp.ingest.rss`.
- `src/podcast_mcp/runpod/client.py` — submits/polls RunPod jobs and performs local speaker-name resolution.
- `src/podcast_mcp/runpod/worker.py` — RunPod serverless handler.
- `src/podcast_mcp/transcribe/pipeline.py` — audio download, Whisper transcription, diarization, speaker-name helper functions.
- `src/podcast_mcp/ingest/transcript.py` — chunks transcript, creates embeddings, writes database records.
- `src/podcast_mcp/mcp/tools.py` — database-backed tool logic.
- `src/podcast_mcp/mcp/server.py` — MCP server exposing tools over stdio or streamable HTTP.
- `src/podcast_mcp/ingest/speaker_names.py` — repairs speaker names for already-ingested episodes without retranscribing.
- `docker-compose.yml` — local/Hetzner services for Postgres, app, scheduler, MCP.
- `Dockerfile.app` — lightweight Hetzner app image.
- `Dockerfile.worker` — RunPod GPU worker image.
- `Dockerfile` — Postgres/pgvector image.
- `db/migrations/` — initial schema.
- `docs/HETZNER.md` — deployment notes.
- `docs/RUNPOD.md` — worker deployment notes.
- `docs/MCP.md` — MCP usage notes.

## Database model

Core tables:

- `episodes`
  - one row per indexed podcast episode
  - unique by `audio_url`
- `episode_speakers`
  - speaker labels per episode
  - includes `speaker_id`, `speaker_name`, `speaker_confidence`, `evidence`
- `transcript_segments`
  - raw transcript segments with timestamps and speaker metadata
- `transcript_chunks`
  - larger searchable chunks with `vector(1536)` embeddings

Old/removed voice-profile tables may exist in local/prod databases from earlier experiments, but current code does not use them.

## MCP tools

Current tools:

- `search_podcast_transcripts`
- `get_episode`
- `get_transcript_around_timestamp`
- `list_episodes`
- `search_by_speaker`

Speaker attribution guidance is embedded in tool descriptions:

- Treat `speaker_name` as certain only when `speaker_confidence >= 0.85`.
- For `0.60 <= speaker_confidence < 0.85`, phrase attribution as likely/probable in the user's language.
- Below `0.60`, avoid firm attribution and mention uncertainty.

The MCP service supports:

- `stdio` for local MCP clients.
- `streamable-http` for remote/public MCP access.
- Bearer token auth via `MCP_BEARER_TOKEN`.
- In-memory IP rate limiting via:
  - `MCP_RATE_LIMIT_REQUESTS`
  - `MCP_RATE_LIMIT_WINDOW_SECONDS`

## Important environment variables

Hetzner app/runtime:

- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `DATABASE_URL`
- `RSS_URL`
- `SYNC_CRON`
- `SYNC_TIMEZONE`
- `SYNC_MAX_EPISODES`
- `SYNC_MAX_RUNTIME_SECONDS`
- `TRANSCRIBE_EXECUTION=runpod`
- `OPENAI_API_KEY`
- `EMBEDDING_MODEL`
- `RUNPOD_API_KEY`
- `RUNPOD_ENDPOINT_ID`
- `RUNPOD_POLL_INTERVAL_SECONDS`
- `RUNPOD_EXECUTION_TIMEOUT_MS`
- `RUNPOD_TTL_MS`
- `SPEAKER_NAME_RESOLUTION_ENABLED`
- `SPEAKER_NAME_MODEL`

MCP HTTP:

- `MCP_TRANSPORT=streamable-http`
- `MCP_BIND_ADDRESS=127.0.0.1`
- `MCP_HOST=0.0.0.0`
- `MCP_PORT=8000`
- `MCP_PUBLIC_URL=https://ai-report.bramdehart.nl`
- `MCP_BEARER_TOKEN`
- `MCP_RATE_LIMIT_REQUESTS=60`
- `MCP_RATE_LIMIT_WINDOW_SECONDS=60`

RunPod worker:

- `TRANSCRIBE_MODEL`
- `TRANSCRIBE_DEVICE`
- `TRANSCRIBE_COMPUTE_TYPE`
- `TRANSCRIBE_BEAM_SIZE`
- `TRANSCRIBE_CHUNK_SECONDS`
- `TRANSCRIBE_LANGUAGE`
- `TRANSCRIBE_HOTWORDS`
- `DIARIZATION_ENABLED`
- `DIARIZATION_MODEL`
- `DIARIZATION_DEVICE`
- `DIARIZATION_MIN_SPEAKERS`
- `DIARIZATION_MAX_SPEAKERS`
- `HUGGINGFACE_TOKEN`

RunPod does not need `OPENAI_API_KEY` for speaker-name resolution in the current architecture, because `podcast_mcp.runpod.client` forces `SPEAKER_NAME_RESOLUTION_ENABLED=false` for the worker and resolves names locally on Hetzner after receiving the transcript.

## Current deployment commands

Start Postgres:

```bash
APP_ENV_FILE=.env.production docker compose up -d postgres
```

Run one sync:

```bash
APP_ENV_FILE=.env.production docker compose --profile tools run --rm --build app
```

Run speaker-name repair without retranscribing:

```bash
APP_ENV_FILE=.env.production docker compose --profile tools run --rm --build app python -m podcast_mcp.ingest.speaker_names
```

Start/recreate scheduler:

```bash
APP_ENV_FILE=.env.production docker compose --profile scheduler up -d --build --force-recreate scheduler
```

Start/recreate MCP:

```bash
APP_ENV_FILE=.env.production docker compose --profile mcp up -d --build --force-recreate mcp
```

View logs with timestamps:

```bash
docker compose --profile scheduler logs --timestamps -f scheduler
docker compose --profile mcp logs --timestamps -f mcp
```

## Public endpoint

Current intended public MCP endpoint:

```text
https://ai-report.bramdehart.nl/mcp/
```

Caddy terminates HTTPS and proxies to:

```text
http://127.0.0.1:8000/mcp/
```

The MCP app itself is bound only to localhost through Docker:

```env
MCP_BIND_ADDRESS=127.0.0.1
```

## Known design choices

- Keep RunPod focused on heavy audio work.
- Keep OpenAI speaker-name resolution on Hetzner for easier secret management.
- Keep embeddings on OpenAI for now; actual costs have been low.
- Use `text-embedding-3-small` with `1536` dimensions.
- Use `gpt-5.4` initially for speaker names, but this is expensive. `gpt-5.4-mini` is likely a better default.
- Speaker-name mapping can be repaired after ingest using `python -m podcast_mcp.ingest.speaker_names`.
- Public MCP access currently uses a demo bearer token rather than per-user registration.
- IP rate limiting is in-memory and suitable for one VPS / one MCP container.

## Known issues and caveats

- Chunked diarization means one real person may have multiple `speaker_id` labels across chunks.
- Claude Desktop may not support remote HTTP MCP directly; `mcp-remote` can bridge it.
- Claude Code CLI supports remote HTTP MCP, but requires a Claude subscription or API billing.
- ChatGPT custom GPTs do not directly consume arbitrary MCP endpoints; a REST/OpenAPI wrapper would be the practical route for GPT Actions.

## Useful database checks

Speaker-name coverage:

```sql
SELECT
  COUNT(*) AS total_speaker_rows,
  COUNT(*) FILTER (WHERE speaker_name IS NOT NULL AND speaker_name <> '') AS named_speaker_rows,
  COUNT(*) FILTER (WHERE speaker_name IS NULL OR speaker_name = '') AS unnamed_speaker_rows
FROM episode_speakers;
```

Unique named people per episode:

```sql
SELECT
  e.titel,
  COUNT(es.speaker_id) AS named_labels,
  COUNT(DISTINCT es.speaker_name) AS unique_named_people,
  STRING_AGG(DISTINCT es.speaker_name, ', ' ORDER BY es.speaker_name) AS names
FROM episode_speakers es
JOIN episodes e ON e.id = es.episode_id
WHERE es.speaker_name IS NOT NULL
  AND es.speaker_name <> ''
GROUP BY e.titel
ORDER BY unique_named_people DESC, named_labels DESC;
```

Transcript chunk count:

```sql
SELECT COUNT(*) FROM transcript_chunks;
```

Segment count:

```sql
SELECT COUNT(*) FROM transcript_segments;
```