# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## 2026-06-01

### Added
- **Initial A2A server** - exposes the Workoflow agent ("Workoflow Bot") over the
  Agent2Agent protocol for A2A-native platforms (Gemini/ADK, SAP Joule). Mirrors
  `workoflow-mcp`'s stateless-proxy role: the only new public surface in front of
  the LAN-only orchestrator.
- **Public agent card** at `/.well-known/agent-card.json` - single `ask-workoflow`
  conversational skill, `capabilities.streaming=True`, HTTP bearer security scheme.
- **Authenticated extended card** at `/agent/authenticatedExtendedCard` - appends
  per-user capability skills resolved from the platform.
- **Executor bridge** (`WorkoflowAgentExecutor`) - reads the bearer credential,
  resolves identity via the platform `POST /api/a2a/resolve`, maps the A2A
  `contextId` to the orchestrator `conversation_id`, streams
  `POST /webhook/stream`, and translates SSE `chunk`/`done` events into A2A
  artifacts with auth/error mapping (`requires_auth` / `failed` / `complete`).
- **Pluggable identity seam** - `IdentityResolver` protocol with phase-1
  `PersonalTokenResolver`; OIDC and SAP IAS resolvers planned behind `AUTH_PHASE`.
- **Observability** - OpenTelemetry tracing (Phoenix) and Sentry error tracking,
  both opt-in via env var presence.
- **Proof scripts** - `proof/jsonrpc_curl.sh` (vendor-neutral) and
  `proof/adk_remote_a2a_proof.py` (Google ADK `RemoteA2aAgent` path).
- **CI** - Docker image build/push to Docker Hub (`patricks1987/workoflow-a2a`)
  and a pytest workflow.
