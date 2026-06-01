"""M2/M4: executor bridges A2A <-> orchestrator (payload shape, SSE->artifact, errors)."""

from collections.abc import AsyncIterator

import pytest
from a2a.server.events import EventQueue
from a2a.types import (
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatusUpdateEvent,
    TextPart,
)

from workoflow_a2a.executor import WorkoflowAgentExecutor, _extract_token
from workoflow_a2a.identity.base import ResolvedIdentity
from workoflow_a2a.orchestrator_client import build_webhook_payload
from workoflow_a2a.platform_client import PlatformAuthError
from workoflow_a2a.sse import SSEEvent


# --- Fakes -----------------------------------------------------------------


class FakeResolver:
    def __init__(self, identity=None, error=None):
        self._identity = identity
        self._error = error

    async def resolve(self, token: str) -> ResolvedIdentity:
        if self._error:
            raise self._error
        return self._identity


class FakeOrchestrator:
    def __init__(self, events):
        self._events = events
        self.calls = []

    async def stream(self, identity, text, conversation_id) -> AsyncIterator[SSEEvent]:
        self.calls.append((identity, text, conversation_id))
        for e in self._events:
            yield e


class FakeRequestContext:
    """Minimal stand-in for a2a RequestContext."""

    class _CallCtx:
        def __init__(self, headers):
            self.state = {"headers": headers}

    def __init__(self, text, context_id="ctx-1", task_id="task-1", headers=None):
        self._text = text
        self.context_id = context_id
        self.task_id = task_id
        self.call_context = self._CallCtx(headers or {})

    def get_user_input(self, delimiter="\n") -> str:
        return self._text


IDENTITY = ResolvedIdentity(
    org_uuid="org-uuid-456",
    workflow_user_id="user-uuid-123",
    email="patrick@company.com",
    display_name="Patrick",
    capabilities=[],
)


async def _drain(event_queue: EventQueue) -> list:
    """Collect everything enqueued, then stop.

    The executor runs to completion synchronously (our fakes never await on the
    network), so by the time ``execute`` returns every event is already on the
    queue. Drain non-blocking until empty.
    """
    import asyncio

    events = []
    while True:
        try:
            events.append(await event_queue.dequeue_event(no_wait=True))
        except asyncio.QueueEmpty:
            break
    return events


def _texts(events) -> str:
    out = []
    for e in events:
        if isinstance(e, TaskArtifactUpdateEvent):
            for p in e.artifact.parts:
                if isinstance(p.root, TextPart):
                    out.append(p.root.text)
    return "".join(out)


def _final_states(events) -> list[TaskState]:
    return [
        e.status.state
        for e in events
        if isinstance(e, TaskStatusUpdateEvent)
    ]


# --- Tests -----------------------------------------------------------------


def test_extract_token_prefers_prompt_token_then_bearer():
    assert _extract_token({"x-prompt-token": "tok1"}) == "tok1"
    assert _extract_token({"Authorization": "Bearer tok2"}) == "tok2"
    assert _extract_token({"authorization": "bearer tok3"}) == "tok3"
    assert _extract_token({}) is None


def test_build_webhook_payload_matches_orchestrator_contract():
    payload = build_webhook_payload(IDENTITY, "Hello", "ctx-9")
    assert payload["text"] == "Hello"
    assert payload["conversation"]["tenantId"] == "org-uuid-456"
    assert payload["custom"]["conversationId"] == "ctx-9"
    assert payload["custom"]["user"]["aadObjectId"] == "user-uuid-123"
    assert payload["custom"]["user"]["email"] == "patrick@company.com"
    assert payload["custom"]["user"]["displayName"] == "Patrick"
    assert payload["from"]["aadObjectId"] == "user-uuid-123"


@pytest.mark.asyncio
async def test_no_token_requires_auth():
    ex = WorkoflowAgentExecutor(resolver=FakeResolver(IDENTITY), orchestrator=FakeOrchestrator([]))
    ctx = FakeRequestContext("hi", headers={})
    eq = EventQueue()
    await ex.execute(ctx, eq)
    events = await _drain(eq)
    assert TaskState.auth_required in _final_states(events)


@pytest.mark.asyncio
async def test_bad_token_requires_auth():
    ex = WorkoflowAgentExecutor(
        resolver=FakeResolver(error=PlatformAuthError("nope")),
        orchestrator=FakeOrchestrator([]),
    )
    ctx = FakeRequestContext("hi", headers={"x-prompt-token": "bad"})
    eq = EventQueue()
    await ex.execute(ctx, eq)
    events = await _drain(eq)
    assert TaskState.auth_required in _final_states(events)


@pytest.mark.asyncio
async def test_nonstreaming_done_emits_artifact_and_completes():
    done = SSEEvent(
        event="done",
        data={
            "type": "final",
            "output": "The answer is 42.",
            "attachment": None,
            "conversationId": "ctx-1",
            "trace_id": "t1",
            "span_id": "s1",
        },
    )
    orch = FakeOrchestrator([done])
    ex = WorkoflowAgentExecutor(resolver=FakeResolver(IDENTITY), orchestrator=orch)
    ctx = FakeRequestContext("question?", headers={"x-prompt-token": "good"})
    eq = EventQueue()
    await ex.execute(ctx, eq)
    events = await _drain(eq)

    # contextId forwarded as conversation_id
    assert orch.calls[0][2] == "ctx-1"
    assert _texts(events) == "The answer is 42."
    assert TaskState.completed in _final_states(events)


@pytest.mark.asyncio
async def test_streaming_chunks_then_complete():
    events_in = [
        SSEEvent(event="status", data={"message": "Processing..."}),
        SSEEvent(event="chunk", data={"text": "Hello "}),
        SSEEvent(event="chunk", data={"text": "world"}),
        SSEEvent(
            event="done",
            data={
                "type": "final",
                "output": "Hello world",
                "attachment": None,
                "conversationId": "ctx-1",
                "trace_id": "t",
                "span_id": "s",
            },
        ),
    ]
    ex = WorkoflowAgentExecutor(
        resolver=FakeResolver(IDENTITY), orchestrator=FakeOrchestrator(events_in)
    )
    ctx = FakeRequestContext("hi", headers={"x-prompt-token": "good"})
    eq = EventQueue()
    await ex.execute(ctx, eq)
    events = await _drain(eq)
    assert _texts(events) == "Hello world"
    assert TaskState.completed in _final_states(events)


@pytest.mark.asyncio
async def test_orchestrator_error_output_maps_to_failed():
    done = SSEEvent(
        event="done",
        data={
            "type": "final",
            "output": "An error occurred: boom. Please try again.",
            "attachment": None,
            "conversationId": "ctx-1",
            "trace_id": "t",
            "span_id": "s",
        },
    )
    ex = WorkoflowAgentExecutor(
        resolver=FakeResolver(IDENTITY), orchestrator=FakeOrchestrator([done])
    )
    ctx = FakeRequestContext("hi", headers={"x-prompt-token": "good"})
    eq = EventQueue()
    await ex.execute(ctx, eq)
    events = await _drain(eq)
    assert TaskState.failed in _final_states(events)


@pytest.mark.asyncio
async def test_stream_without_done_fails():
    ex = WorkoflowAgentExecutor(
        resolver=FakeResolver(IDENTITY),
        orchestrator=FakeOrchestrator([SSEEvent(event="chunk", data={"text": "x"})]),
    )
    ctx = FakeRequestContext("hi", headers={"x-prompt-token": "good"})
    eq = EventQueue()
    await ex.execute(ctx, eq)
    events = await _drain(eq)
    assert TaskState.failed in _final_states(events)
