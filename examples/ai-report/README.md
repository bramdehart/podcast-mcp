# AI Report deployment example

This directory is a concrete production deployment of Podcast MCP powering
[AI Report](https://www.aireport.nl/). It is one example configuration of the
generic repository and is not required to run the core MCP server.

## Services

- `postgres` — Postgres with pgvector, schema applied from `db/migrations/`.
- `app` — one-off container for manual commands such as RSS sync.
- `scheduler` — long-running RSS sync based on `SYNC_CRON`.
- `mcp` — the MCP HTTP service, bound to localhost, exposed publicly through Caddy.

GPU transcription and diarization stay on RunPod.

## Environment

Create a server-local env file, for example `.env.production`. Do not commit it.

The required variables are documented in `docs/deployment/hetzner.md` and
`docs/configuration.md`.

## Commands

Start the database:

```bash
APP_ENV_FILE=.env.production docker compose up -d postgres
```

Run one manual RSS sync:

```bash
APP_ENV_FILE=.env.production docker compose --profile tools run --rm app
```

Resolve missing speaker names without retranscribing:

```bash
APP_ENV_FILE=.env.production docker compose --profile tools run --rm app podcast-mcp-speaker-names
```

Start the scheduler:

```bash
APP_ENV_FILE=.env.production docker compose --profile scheduler up -d scheduler
```

Start the MCP service:

```bash
APP_ENV_FILE=.env.production docker compose --profile mcp up -d mcp
```

## RunPod worker image

Build and push the worker image:

```bash
docker build -f Dockerfile.worker -t ghcr.io/<owner>/podcast-mcp-worker:latest ../..
docker push ghcr.io/<owner>/podcast-mcp-worker:latest
```

The GitHub Actions workflow `.github/workflows/publish-worker-image.yml` does
this automatically on pushes to `main` and can be triggered manually.

## First smoke test

1. Start Postgres.
2. Run one manual sync with `SYNC_MAX_EPISODES=1`.
3. Confirm an episode was stored.
4. Start the scheduler only after the manual sync succeeds.
5. Add the public MCP service only after auth and rate limiting are enabled.