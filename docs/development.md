# Development

## Setup

Requires Python 3.12+.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ".[server,ingestion,worker,dev]"
cp .env.example .env
```

The package uses `src/` layout. Install it with `pip install -e .` so the CLI
entry points are available:

- `podcast-mcp` — run the MCP server.
- `podcast-mcp-tools` — query transcripts from the command line.
- `podcast-mcp-ingest` — run one RSS sync.
- `podcast-mcp-scheduler` — run the cron-style RSS scheduler.
- `podcast-mcp-speaker-names` — repair missing speaker names.
- `podcast-mcp-transcribe` — transcribe one audio URL locally.
- `podcast-mcp-runpod` — submit one audio URL to RunPod.

## Dependency groups

Dependencies are split by workload so a plain MCP server install stays small:

| Group | Purpose |
| ----- | ------- |
| base  | Core package: `psycopg`, `requests`, `python-dotenv`. |
| `server` | MCP server: `mcp`, `uvicorn`. |
| `ingestion` | RSS sync, scheduler, ingest: `croniter`. |
| `worker` | GPU transcription/diarization: `faster-whisper`, `pyannote.audio`, `torchcodec`, `runpod`. |
| `dev` | `ruff`, `pytest`, `mypy`. |

Only install what you need:

```bash
pip install -e ".[server]"        # MCP server only
pip install -e ".[server,ingestion]"  # server + ingestion
pip install -e ".[worker]"        # GPU worker only
```

## Tests

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests
```

Unit tests live in `tests/unit`. Integration tests in `tests/integration`
require a reachable `DATABASE_URL` and are skipped otherwise.

## Linting and type checking

```bash
.venv/bin/python -m ruff check src tests
.venv/bin/python -m mypy src/podcast_mcp
```

## Running the MCP server

Stdio (for local MCP clients):

```bash
podcast-mcp
```

Streamable HTTP with bearer auth:

```bash
MCP_TRANSPORT=streamable-http MCP_BEARER_TOKEN=$(openssl rand -hex 32) podcast-mcp
```

## Running a one-off RSS sync

```bash
podcast-mcp-ingest
```

The scheduler wraps this with `SYNC_CRON`:

```bash
podcast-mcp-scheduler
```

## Inspecting the database

Common checks:

```sql
SELECT COUNT(*) FROM transcript_chunks;
SELECT COUNT(*) FROM transcript_segments;
```

Speaker-name coverage:

```sql
SELECT
  COUNT(*) AS total_speaker_rows,
  COUNT(*) FILTER (WHERE speaker_name IS NOT NULL AND speaker_name <> '') AS named_speaker_rows,
  COUNT(*) FILTER (WHERE speaker_name IS NULL OR speaker_name = '') AS unnamed_speaker_rows
FROM episode_speakers;
```