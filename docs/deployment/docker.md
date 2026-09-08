# Docker deployment

The repository ships a minimal Docker Compose setup for local development that
runs Postgres with pgvector and the migrations.

## Local development database

Start Postgres:

```bash
docker compose up -d postgres
```

This builds the `pgvector/pgvector` image and copies `db/migrations/` into the
init directory, so the schema is applied on first start.

## Full production stack (AI Report example)

The production deployment that powers [AI Report](https://www.aireport.nl/) is
kept as a concrete example in [`examples/ai-report/`](../../examples/ai-report/).
It adds `app`, `scheduler`, and `mcp` services on top of Postgres, plus
`Dockerfile.app` and `Dockerfile.worker` images.

See `examples/ai-report/README.md` for setup and commands.