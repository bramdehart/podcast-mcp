# Podcast RAG MCP tools

This project exposes the indexed podcast database as MCP tools.

## Tools

- `search_podcast_transcripts` searches transcript chunks semantically with pgvector.
- `get_episode` returns episode metadata and speaker mappings.
- `get_transcript_around_timestamp` returns raw transcript segments around a timestamp.
- `list_episodes` lists indexed episodes.
- `search_by_speaker` searches or lists chunks spoken by a specific speaker.

## Requirements

The tools expect:

- `DATABASE_URL` pointing to the Postgres database.
- `OPENAI_API_KEY` with embeddings request permission.
- `EMBEDDING_MODEL=text-embedding-3-small`.
- `EMBEDDING_DIMENSIONS=1536`.

Install dependencies after pulling changes:

```bash
.venv/bin/pip install -r requirements.txt
```

## Run as MCP server

```bash
.venv/bin/python podcast_mcp_server.py
```

Example Codex MCP config:

```toml
[mcp_servers.podcast-rag]
command = "/absolute/path/to/podcast-rag/.venv/bin/python"
args = ["/absolute/path/to/podcast-rag/podcast_mcp_server.py"]
cwd = "/absolute/path/to/podcast-rag"
```

## Run from CLI

List indexed episodes:

```bash
.venv/bin/python podcast_tools.py list-episodes
```

Semantic search:

```bash
.venv/bin/python podcast_tools.py search "wat werd er gezegd over Anthropic?"
```

Fetch transcript context:

```bash
.venv/bin/python podcast_tools.py around "<episode-id>" 1234 --context-seconds 90
```

Search by speaker:

```bash
.venv/bin/python podcast_tools.py speaker --speaker-name "Alexander" --query "Anthropic"
```
