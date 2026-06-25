# Podcast MCP tools

This project exposes the indexed podcast database as MCP tools.

## Tools

- `search_podcast_transcripts` searches transcript chunks semantically with pgvector.
- `get_episode` returns episode metadata and speaker mappings.
- `get_transcript_around_timestamp` returns raw transcript segments around a timestamp.
- `list_episodes` lists indexed episodes.
- `search_by_speaker` searches or lists chunks spoken by a specific speaker.

## Speaker attribution

Speaker names are inferred from diarization and transcript context. Use `speaker_confidence` when answering:

- Treat `speaker_name` as certain only when `speaker_confidence >= 0.85`.
- For `0.60 <= speaker_confidence < 0.85`, phrase attribution as likely/probable in the user's language.
- Below `0.60`, avoid firm attribution and mention that the speaker identity is uncertain.

## Requirements

The tools expect:

- `DATABASE_URL` pointing to the Postgres database.
- `OPENAI_API_KEY` with embeddings request permission.
- `EMBEDDING_MODEL=text-embedding-3-small`.

Install dependencies after pulling changes:

```bash
.venv/bin/pip install -r requirements.txt
```

## Run as MCP server

```bash
PYTHONPATH=src .venv/bin/python -m podcast_mcp.mcp.server
```

Example Codex MCP config:

```toml
[mcp_servers.podcast-mcp]
command = "/absolute/path/to/podcast-mcp/.venv/bin/python"
args = ["-m", "podcast_mcp.mcp.server"]
cwd = "/absolute/path/to/podcast-mcp"
env = { PYTHONPATH = "/absolute/path/to/podcast-mcp/src" }
```

## Run from CLI

List indexed episodes:

```bash
PYTHONPATH=src .venv/bin/python -m podcast_mcp.mcp.tools list-episodes
```

Semantic search:

```bash
PYTHONPATH=src .venv/bin/python -m podcast_mcp.mcp.tools search "wat werd er gezegd over Anthropic?"
```

Fetch transcript context:

```bash
PYTHONPATH=src .venv/bin/python -m podcast_mcp.mcp.tools around "<episode-id>" 1234 --context-seconds 90
```

Search by speaker:

```bash
PYTHONPATH=src .venv/bin/python -m podcast_mcp.mcp.tools speaker --speaker-name "Alexander" --query "Anthropic"
```

## Scheduled RSS sync

Use a cron expression in `SYNC_CRON` to schedule RSS syncs. The default runs every Friday at 06:00 in `Europe/Amsterdam`:

```env
SYNC_CRON=0 6 * * 5
SYNC_TIMEZONE=Europe/Amsterdam
```

Run the scheduler:

```bash
PYTHONPATH=src .venv/bin/python -m podcast_mcp.ingest.scheduler
```
