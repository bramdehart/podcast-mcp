# Security Policy

## Supported versions

| Version | Supported |
| ------- | --------- |
| 0.1.x   | ✅        |

## Authentication model

The MCP server can be served over `stdio` (local MCP clients) or over
`streamable-http` / `sse` (remote access).

Remote transports require a bearer token set via `MCP_BEARER_TOKEN`:

```env
MCP_TRANSPORT=streamable-http
MCP_BEARER_TOKEN=<strong-random-token>
```

The server rejects HTTP requests without a valid `Authorization: Bearer <token>`
header when `MCP_BEARER_TOKEN` is set. The token is compared using a constant-time
comparison (`hmac.compare_digest`).

The public demo endpoint in the README uses a read-only demo token that is rate
limited by IP:

- `MCP_RATE_LIMIT_REQUESTS` — maximum requests per IP per window.
- `MCP_RATE_LIMIT_WINDOW_SECONDS` — sliding window length in seconds.

Rate limiting is in-memory and suitable for a single MCP container / VPS.

## Secrets

- Never commit real secrets. The repository is public.
- Use `.env` locally and `.env.production` on deployment servers; both are
  gitignored. Copy `.env.example` to get started.
- The demo bearer token, OpenAI, RunPod, and Hugging Face credentials in the
  README/`.env.example` are placeholders or intentionally public demo values.
  Rotate them before using in production.
- Report accidental secret exposure immediately and rotate the affected secret.

## Security assumptions

- The MCP tools are read-only. There is no write path through the MCP interface.
- Transcription and diarization secrets (`OPENAI_API_KEY`,
  `HUGGINGFACE_TOKEN`, `RUNPOD_API_KEY`) are only used by the ingestion and
  worker processes, never by the MCP server itself.
- The MCP server should be bound to `127.0.0.1` and exposed publicly only
  through a TLS-terminating reverse proxy (for example Caddy) that sits in
  front of the bearer-token-authenticated HTTP endpoint.

## Reporting a vulnerability

Please report security issues privately. Do not open a public issue for
security problems.

- Email: `security@bramdehart.nl`
- Include: affected version, a description of the issue, and (if possible) a
  minimal reproduction.

You will receive a response within 72 hours. We ask that you do not disclose
the issue publicly until it has been triaged and (if applicable) a fix has
been released.

## Dependencies

Keep dependencies up to date. The project pins exact versions for the main
runtime dependencies in `pyproject.toml` so that builds are reproducible.