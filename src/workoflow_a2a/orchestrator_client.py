"""Streaming client for the orchestrator ``POST /webhook/stream`` endpoint.

The orchestrator is LAN-only and unchanged. We build the exact
``WebhookPayload``-shaped JSON its ``payload_parser.parse_payload`` already
reads, authenticate with the shared ``WEBHOOK_AUTH_TOKEN`` bearer, and stream
back the SSE events.

Inbound payload field paths the orchestrator reads (verified against
``workoflow-orchestrator/src/webhook/payload_parser.py``):

- ``text``                          -> the user message
- ``conversation.tenantId``         -> org_uuid (routing / session key)
- ``custom.conversationId``         -> conversation_id (session thread)
- ``custom.user.aadObjectId``       -> workflow_user_id (1st priority)
- ``custom.user.email``             -> user_email
- ``custom.user.displayName``       -> user_name
- ``from.aadObjectId``              -> workflow_user_id (fallback)

SSE events it emits (``streaming.py``): one ``status``, zero-or-more ``chunk``
(``{"text": <delta>}``), one terminal ``done``
(``{"type":"final","output":..,"attachment":..,"conversationId":..,"trace_id":..,"span_id":..}``).
There is no ``last_chunk`` field; ``done`` terminates the stream.
"""

from collections.abc import AsyncIterator

import httpx

from workoflow_a2a.config import get_settings
from workoflow_a2a.identity.base import ResolvedIdentity
from workoflow_a2a.sse import SSEEvent, parse_sse


def build_webhook_payload(
    identity: ResolvedIdentity,
    text: str,
    conversation_id: str,
) -> dict:
    """Build the orchestrator-compatible webhook payload from A2A inputs.

    ``conversation_id`` is the A2A ``contextId``; it maps directly onto the
    orchestrator's Redis thread key
    ``adk:session:{org_uuid}:{workflow_user_id}:{conversation_id}``.
    """
    return {
        "text": text,
        "from": {
            "id": identity.workflow_user_id,
            "name": identity.display_name,
            "aadObjectId": identity.workflow_user_id,
        },
        "conversation": {
            "tenantId": identity.org_uuid,
        },
        "custom": {
            "conversationId": conversation_id,
            "user": {
                "aadObjectId": identity.workflow_user_id,
                "email": identity.email,
                "displayName": identity.display_name,
            },
        },
    }


class OrchestratorClient:
    """Streams the orchestrator webhook and yields decoded SSE events."""

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.orchestrator_url_clean
        self.auth_token = settings.webhook_auth_token
        self.timeout = settings.orchestrator_timeout_seconds

    async def stream(
        self,
        identity: ResolvedIdentity,
        text: str,
        conversation_id: str,
    ) -> AsyncIterator[SSEEvent]:
        """POST the webhook payload and yield each SSE event as it arrives."""
        payload = build_webhook_payload(identity, text, conversation_id)
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        timeout = httpx.Timeout(self.timeout, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/webhook/stream",
                json=payload,
                headers=headers,
            ) as response:
                response.raise_for_status()
                async for event in parse_sse(response.aiter_lines()):
                    yield event
