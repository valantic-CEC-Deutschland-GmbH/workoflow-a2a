"""SSE parser: reassembles the orchestrator's event/data frames."""

from collections.abc import AsyncIterator

import pytest

from workoflow_a2a.sse import parse_sse


async def _lines(*chunks: str) -> AsyncIterator[str]:
    # Mimic httpx.aiter_lines(): yields lines without trailing newlines.
    text = "".join(chunks)
    for line in text.split("\n"):
        yield line


@pytest.mark.asyncio
async def test_parses_status_chunk_done_sequence():
    raw = (
        'event: status\ndata: {"type": "informative", "message": "Processing..."}\n\n'
        'event: chunk\ndata: {"text": "Hello "}\n\n'
        'event: chunk\ndata: {"text": "world"}\n\n'
        'event: done\ndata: {"type": "final", "output": "Hello world", '
        '"attachment": null, "conversationId": "ctx-1", '
        '"trace_id": "abc", "span_id": "def"}\n\n'
    )
    events = [e async for e in parse_sse(_lines(raw))]
    assert [e.event for e in events] == ["status", "chunk", "chunk", "done"]
    assert events[1].data["text"] == "Hello "
    assert events[3].data["output"] == "Hello world"
    assert events[3].data["trace_id"] == "abc"


@pytest.mark.asyncio
async def test_invalid_json_is_wrapped_not_raised():
    raw = "event: chunk\ndata: not-json\n\n"
    events = [e async for e in parse_sse(_lines(raw))]
    assert events[0].data == {"raw": "not-json"}
