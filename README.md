# Workoflow A2A Server

A2A (Agent2Agent) server that exposes your Workoflow organization's AI agent to
external A2A-native platforms (Google Gemini / ADK / Vertex, SAP Joule, ...) as a
consumable agent - "Workoflow Bot". It is the A2A analog of the
[`workoflow-mcp`](https://github.com/valantic-CEC-Deutschland-GmbH/workoflow-mcp)
server: a thin, stateless, public proxy in front of the LAN-only orchestrator.

## What it is (and is not)

- **A2A server** for A2A-native clients (Gemini/ADK, SAP Joule). They discover us
  via the public agent card and call `message/send` / `message/stream`.
- **Not for Claude / ChatGPT** - those are MCP clients and already consume
  Workoflow through `workoflow-mcp`. They reach an A2A server only via a
  community MCP<->A2A bridge, which this project does not build.

## Topology

```
External A2A client (Gemini/ADK, SAP Joule)
  │  HTTPS  GET /.well-known/agent-card.json   (PUBLIC, unauthenticated discovery)
  │  HTTPS  POST /  message/send|stream         (PUBLIC, bearer = personal token)
  ▼
workoflow-a2a   (this repo - PUBLIC, stateless; container :9000)
  ├─ POST {platform}/api/a2a/resolve     (token -> org_uuid, workflow_user_id, email, capabilities)
  └─ POST {orchestrator}/webhook/stream  (LAN, Bearer WEBHOOK_AUTH_TOKEN; SSE chunks)
       ▼
   workoflow-orchestrator  (LAN-ONLY, unchanged - builds the per-user agent)
```

The orchestrator stays private. `workoflow-a2a` is the only new public surface
and is a thin translator (A2A <-> the orchestrator webhook), exactly like
`workoflow-mcp` is for MCP.

## Authentication

Phase 1 uses your Workoflow **personal access token** (from `/profile/`) as the
A2A bearer credential (also accepted via the `X-Prompt-Token` header). The
server forwards it to the platform's `POST /api/a2a/resolve`, which maps it to
your identity and enabled capabilities.

The identity layer is a pluggable seam (`src/workoflow_a2a/identity/`):

| Phase | Resolver | Card advertises | Status |
|---|---|---|---|
| 1 | `PersonalTokenResolver` | HTTP bearer | implemented |
| 2 | `OidcResolver` | OAuth2 / OIDC | planned |
| 3 | `IasResolver` (SAP IAS App2App) | OIDC at the IAS issuer | planned |

Switching phases is a DI + agent-card `security_schemes` change keyed off
`AUTH_PHASE`; the executor never changes.

## Endpoints

| Path | Auth | Purpose |
|---|---|---|
| `GET /.well-known/agent-card.json` | none | Public discovery card (single `ask-workoflow` skill) |
| `GET /.well-known/agent.json` | none | Legacy alias (deprecated by the SDK) |
| `POST /` | bearer | JSON-RPC `message/send` and `message/stream` |
| `GET /agent/authenticatedExtendedCard` | bearer | Per-user card with capability skills |

## Quick Start

### 1. Get your token
Log into Workoflow -> `/profile/` -> copy your Personal Access Token.

### 2. Run locally
```bash
pip install -r requirements.txt
cp .env.example .env   # set ORCHESTRATOR_URL, WEBHOOK_AUTH_TOKEN, WORKOFLOW_API_URL
uvicorn workoflow_a2a.app:app --host 0.0.0.0 --port 9008
```

### 3. Docker
```bash
docker build -t workoflow-a2a .
docker run -p 9008:9000 --env-file .env workoflow-a2a
```

## Proof / verification

```bash
# Vendor-neutral JSON-RPC (discover + message/send, twice with same contextId):
A2A_URL=http://localhost:9008 TOKEN=<personal-token> ./proof/jsonrpc_curl.sh

# Google ADK RemoteA2aAgent path (what Gemini/ADK use):
pip install -e '.[proof]'
A2A_CARD_URL=http://localhost:9008/.well-known/agent-card.json TOKEN=<token> \
  python proof/adk_remote_a2a_proof.py "Who knows Kubernetes?"
```

## Tests
```bash
pip install -e '.[dev]'
pytest
```

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `WORKOFLOW_API_URL` | `http://host.docker.internal:3979` | Platform base URL (token resolve) |
| `ORCHESTRATOR_URL` | `http://adk-orchestrator:8080` | LAN orchestrator base URL |
| `WEBHOOK_AUTH_TOKEN` | (empty) | Shared bearer for the orchestrator webhook |
| `ORCHESTRATOR_TIMEOUT_SECONDS` | `600` | Stream timeout |
| `PUBLIC_BASE_URL` | `http://localhost:9008` | Public URL advertised in the card |
| `AGENT_NAME` | `Workoflow Bot` | Card name |
| `AUTH_PHASE` | `personal_token` | Identity resolver selector |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | (unset) | Enables OpenTelemetry tracing (Phoenix) |
| `OTEL_SERVICE_NAME` | `workoflow-a2a` | OTEL service name |
| `SENTRY_DSN` | (empty) | Enables Sentry error tracking |
| `SENTRY_ENVIRONMENT` | `development` | Sentry environment |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.0` | Sentry trace sampling |

## Source layout

| File | Purpose |
|---|---|
| `src/workoflow_a2a/app.py` | ASGI entrypoint; `A2AStarletteApplication` + extended-card modifier |
| `src/workoflow_a2a/config.py` | `pydantic-settings` configuration |
| `src/workoflow_a2a/agent_card.py` | Public + extended agent card builders |
| `src/workoflow_a2a/executor.py` | The A2A <-> orchestrator bridge (`AgentExecutor`) |
| `src/workoflow_a2a/orchestrator_client.py` | Streams `POST /webhook/stream`; builds the webhook payload |
| `src/workoflow_a2a/platform_client.py` | `POST /api/a2a/resolve` client |
| `src/workoflow_a2a/identity/` | `IdentityResolver` protocol + `PersonalTokenResolver` |
| `src/workoflow_a2a/sse.py` | Minimal SSE line parser |
| `src/workoflow_a2a/observability.py` | OpenTelemetry + Sentry setup |
