"""Minimal SSE line parser for the orchestrator's ``text/event-stream`` output.

The orchestrator emits frames in the exact form::

    event: <name>\n
    data: <json>\n
    \n

(see ``workoflow-orchestrator/src/webhook/streaming.py::format_sse``). We only
need to reassemble ``event`` + ``data`` pairs from a line iterator; this keeps
the dependency surface to ``httpx`` alone.
"""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass
class SSEEvent:
    """A single decoded server-sent event."""

    event: str
    data: dict


async def parse_sse(lines: AsyncIterator[str]) -> AsyncIterator[SSEEvent]:
    """Yield :class:`SSEEvent` objects from an async iterator of raw lines.

    Lines arrive without trailing newlines (``httpx.aiter_lines``). A blank line
    dispatches the accumulated event. ``data:`` payloads are JSON-decoded; on a
    decode error the event is skipped rather than crashing the stream.
    """
    event_name = "message"
    data_buf: list[str] = []

    async for raw in lines:
        line = raw.rstrip("\r")
        if line == "":
            if data_buf:
                raw_data = "\n".join(data_buf)
                try:
                    payload = json.loads(raw_data)
                except json.JSONDecodeError:
                    payload = {"raw": raw_data}
                yield SSEEvent(event=event_name, data=payload)
            event_name = "message"
            data_buf = []
            continue
        if line.startswith(":"):
            # comment / heartbeat
            continue
        if line.startswith("event:"):
            event_name = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_buf.append(line[len("data:"):].lstrip())

    # Flush a trailing event with no closing blank line.
    if data_buf:
        raw_data = "\n".join(data_buf)
        try:
            payload = json.loads(raw_data)
        except json.JSONDecodeError:
            payload = {"raw": raw_data}
        yield SSEEvent(event=event_name, data=payload)
