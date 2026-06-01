"""End-to-end through the real A2AStarletteApplication.

Drives JSON-RPC ``message/send`` over the actual ASGI app, with the platform
resolve and orchestrator stream patched. Proves the executor wires correctly
into the SDK request handler (not just in isolation) and that the extended card
enriches per-user skills.
"""

from collections.abc import AsyncIterator

import httpx
import pytest

from workoflow_a2a.identity.base import ResolvedIdentity
from workoflow_a2a.sse import SSEEvent

IDENTITY = ResolvedIdentity(
    org_uuid="org-uuid-456",
    workflow_user_id="user-uuid-123",
    email="patrick@company.com",
    display_name="Patrick",
    capabilities=[{"type": "orchestrator.people_finder", "name": "People Finder"}],
)


class FakeResolver:
    async def resolve(self, token):
        return IDENTITY


class FakeOrchestrator:
    async def stream(self, identity, text, conversation_id) -> AsyncIterator[SSEEvent]:
        yield SSEEvent(event="status", data={"message": "Processing..."})
        yield SSEEvent(event="chunk", data={"text": "Hello "})
        yield SSEEvent(event="chunk", data={"text": text})
        yield SSEEvent(
            event="done",
            data={
                "type": "final",
                "output": f"Hello {text}",
                "attachment": None,
                "conversationId": conversation_id,
                "trace_id": "t",
                "span_id": "s",
            },
        )


@pytest.fixture
def app(monkeypatch):
    """Build a fresh app whose executor + extended-card use the fakes."""
    # The extended-card modifier resolves the token via get_resolver(); patch it
    # in the app module's namespace (where it is referenced).
    import workoflow_a2a.app as app_mod
    from a2a.server.apps import A2AStarletteApplication
    from a2a.server.request_handlers import DefaultRequestHandler
    from a2a.server.tasks import InMemoryTaskStore
    from workoflow_a2a.executor import WorkoflowAgentExecutor

    monkeypatch.setattr(app_mod, "get_resolver", lambda: FakeResolver())

    executor = WorkoflowAgentExecutor(
        resolver=FakeResolver(), orchestrator=FakeOrchestrator()
    )
    handler = DefaultRequestHandler(
        agent_executor=executor, task_store=InMemoryTaskStore()
    )
    a2a_app = A2AStarletteApplication(
        agent_card=app_mod._public_card,
        http_handler=handler,
        extended_card_modifier=app_mod._extended_card_modifier,
    )
    return a2a_app.build()


@pytest.mark.asyncio
async def test_message_send_returns_orchestrator_answer(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        body = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "kind": "message",
                    "messageId": "m1",
                    "contextId": "ctx-1",
                    "parts": [{"kind": "text", "text": "world"}],
                }
            },
        }
        r = await c.post(
            "/",
            json=body,
            headers={"Authorization": "Bearer some-token"},
        )
        assert r.status_code == 200
        result = r.json()["result"]
        assert result["status"]["state"] == "completed"
        # The streamed chunks are appended as artifact parts; concatenated they
        # form the orchestrator's answer.
        parts_text = "".join(
            p.get("text", "")
            for a in result.get("artifacts", [])
            for p in a.get("parts", [])
        )
        assert parts_text == "Hello world"


@pytest.mark.asyncio
async def test_extended_card_lists_capability_skills(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get(
            "/agent/authenticatedExtendedCard",
            headers={"Authorization": "Bearer some-token"},
        )
        assert r.status_code == 200
        card = r.json()
        ids = [s["id"] for s in card["skills"]]
        assert "ask-workoflow" in ids
        assert "orchestrator.people_finder" in ids
