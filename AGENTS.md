# Workoflow A2A Server

Python A2A (Agent2Agent) server exposing the Workoflow agent to A2A-native
platforms (Gemini/ADK, SAP Joule). Stateless public proxy in front of the
LAN-only orchestrator - the A2A analog of `workoflow-mcp`.

## Quick Reference

- **Tech**: Python 3.11+, a2a-sdk (Starlette ASGI), httpx, pydantic-settings
- **Port**: 9008 (host) -> 9000 (container)

```bash
# Install
pip install -e '.[dev]'

# Run locally
uvicorn workoflow_a2a.app:app --host 0.0.0.0 --port 9008

# Docker
docker build -t workoflow-a2a .
docker run -p 9008:9000 --env-file .env workoflow-a2a

# Tests
pytest

# Proof (Google ADK client path)
pip install -e '.[proof]'
python proof/adk_remote_a2a_proof.py "Who knows Kubernetes?"
```

## Architecture

A2A request -> `WorkoflowAgentExecutor` -> resolve token at platform
`/api/a2a/resolve` -> stream orchestrator `/webhook/stream` -> translate SSE
`chunk`/`done` into A2A artifacts. The orchestrator is never modified; the A2A
`contextId` is forwarded as the orchestrator `conversation_id` so the 30-day
Redis thread is reused.

## Source Layout

| File | Purpose |
|------|---------|
| `src/workoflow_a2a/app.py` | ASGI app: `A2AStarletteApplication` + extended-card modifier |
| `src/workoflow_a2a/executor.py` | A2A <-> orchestrator bridge |
| `src/workoflow_a2a/orchestrator_client.py` | webhook payload + SSE stream |
| `src/workoflow_a2a/platform_client.py` | `/api/a2a/resolve` client |
| `src/workoflow_a2a/agent_card.py` | public + extended cards |
| `src/workoflow_a2a/identity/` | `IdentityResolver` + `PersonalTokenResolver` |
| `src/workoflow_a2a/config.py` | settings | 

## Environment

See `.env.example`. Key vars: `WORKOFLOW_API_URL`, `ORCHESTRATOR_URL`,
`WEBHOOK_AUTH_TOKEN`, `PUBLIC_BASE_URL`, `OTEL_EXPORTER_OTLP_ENDPOINT`,
`SENTRY_DSN`.

## Skills

Use `workoflow-skills` (`/add-dir ../workoflow-skills`) for: `architecture`,
`dev-setup`, `mcp-dev` (sibling proxy pattern).
