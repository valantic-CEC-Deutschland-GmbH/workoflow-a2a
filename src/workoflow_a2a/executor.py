"""The A2A <-> orchestrator bridge.

``WorkoflowAgentExecutor`` is fully stateless. Per request it:

1. Reads the bearer credential from the inbound HTTP headers
   (``x-prompt-token`` or ``Authorization: Bearer``). None -> ``requires_auth``.
2. Resolves the credential to a Workoflow user via the identity resolver.
3. Uses the A2A ``contextId`` directly as the orchestrator ``conversation_id``
   (no mapping store - the orchestrator reuses its 30-day Redis thread).
4. Streams ``POST /webhook/stream`` and translates events to A2A:
   - ``chunk`` deltas -> appended ``TextPart`` artifact chunks (streaming).
   - terminal ``done`` -> final artifact + ``complete()`` (or ``failed()`` on
     an error ``output``).
   - platform 401 -> ``requires_auth()``; network/orchestrator error -> ``failed()``.
"""

import logging

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, TextPart
from a2a.utils import new_agent_text_message

from workoflow_a2a.identity import IdentityResolver, get_resolver
from workoflow_a2a.orchestrator_client import OrchestratorClient
from workoflow_a2a.platform_client import PlatformAuthError

logger = logging.getLogger(__name__)

ARTIFACT_ID = "workoflow-response"
ARTIFACT_NAME = "response"

# Prefix the orchestrator uses for all error terminal outputs
# (workoflow-orchestrator/src/webhook/streaming.py).
_ERROR_PREFIX = "An error occurred:"


def _extract_token(headers: dict[str, str]) -> str | None:
    """Read the bearer credential from inbound headers (case-insensitive)."""
    lowered = {k.lower(): v for k, v in headers.items()}
    token = lowered.get("x-prompt-token")
    if token:
        return token
    auth = lowered.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


class WorkoflowAgentExecutor(AgentExecutor):
    """Bridges A2A requests to the orchestrator webhook stream."""

    def __init__(
        self,
        resolver: IdentityResolver | None = None,
        orchestrator: OrchestratorClient | None = None,
    ) -> None:
        self._resolver = resolver or get_resolver()
        self._orchestrator = orchestrator or OrchestratorClient()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(
            event_queue,
            task_id=context.task_id,
            context_id=context.context_id,
        )

        # 1. Auth - read bearer from inbound headers.
        headers: dict[str, str] = {}
        if context.call_context is not None:
            headers = context.call_context.state.get("headers", {}) or {}
        token = _extract_token(headers)
        if not token:
            await updater.requires_auth(
                message=new_agent_text_message(
                    "Authentication required: provide your Workoflow personal "
                    "access token as a bearer token (or X-Prompt-Token header).",
                    context_id=context.context_id,
                    task_id=context.task_id,
                ),
                final=True,
            )
            return

        # 2. Resolve identity.
        try:
            identity = await self._resolver.resolve(token)
        except PlatformAuthError:
            await updater.requires_auth(
                message=new_agent_text_message(
                    "The provided token was rejected by the Workoflow platform.",
                    context_id=context.context_id,
                    task_id=context.task_id,
                ),
                final=True,
            )
            return
        except Exception as exc:  # noqa: BLE001 - surface as task failure
            logger.exception("Identity resolution failed")
            await updater.failed(
                message=new_agent_text_message(
                    f"Failed to resolve identity: {exc}",
                    context_id=context.context_id,
                    task_id=context.task_id,
                )
            )
            return

        # 3. contextId -> conversation_id (reuses the orchestrator Redis thread).
        conversation_id = context.context_id or ""
        text = context.get_user_input()

        # 4. Stream the orchestrator and translate events.
        await updater.start_work()
        started_artifact = False
        try:
            async for sse in self._orchestrator.stream(identity, text, conversation_id):
                if sse.event == "chunk":
                    delta = sse.data.get("text", "")
                    if not delta:
                        continue
                    await updater.add_artifact(
                        parts=[Part(root=TextPart(text=delta))],
                        artifact_id=ARTIFACT_ID,
                        name=ARTIFACT_NAME,
                        append=started_artifact,
                        last_chunk=False,
                    )
                    started_artifact = True
                elif sse.event == "done":
                    await self._finish(updater, context, sse.data, started_artifact)
                    return
                # 'status' and any other events are informational; ignore.

            # Stream ended without a 'done' event - treat as failure.
            await updater.failed(
                message=new_agent_text_message(
                    "The orchestrator stream ended without a final response.",
                    context_id=context.context_id,
                    task_id=context.task_id,
                )
            )
        except Exception as exc:  # noqa: BLE001 - network / orchestrator error
            logger.exception("Orchestrator stream failed")
            await updater.failed(
                message=new_agent_text_message(
                    f"Failed to reach the Workoflow orchestrator: {exc}",
                    context_id=context.context_id,
                    task_id=context.task_id,
                )
            )

    async def _finish(
        self,
        updater: TaskUpdater,
        context: RequestContext,
        done: dict,
        started_artifact: bool,
    ) -> None:
        """Emit the final artifact and close the task from a ``done`` event."""
        output = done.get("output") or ""
        attachment = done.get("attachment")
        metadata = {
            "conversation_id": done.get("conversationId") or context.context_id,
            "trace_id": done.get("trace_id"),
            "span_id": done.get("span_id"),
        }
        if attachment:
            metadata["attachment"] = attachment

        # The orchestrator signals errors via the output text, not a distinct event.
        is_error = isinstance(output, str) and output.startswith(_ERROR_PREFIX)

        if not started_artifact:
            # Non-streaming path (M2): emit the whole output as one artifact.
            await updater.add_artifact(
                parts=[Part(root=TextPart(text=output))],
                artifact_id=ARTIFACT_ID,
                name=ARTIFACT_NAME,
                metadata=metadata,
                last_chunk=True,
            )
        else:
            # Streaming path (M4): close the appended artifact with a final empty
            # chunk carrying correlation metadata.
            await updater.add_artifact(
                parts=[Part(root=TextPart(text=""))],
                artifact_id=ARTIFACT_ID,
                name=ARTIFACT_NAME,
                metadata=metadata,
                append=True,
                last_chunk=True,
            )

        if is_error:
            await updater.failed(
                message=new_agent_text_message(
                    output,
                    context_id=context.context_id,
                    task_id=context.task_id,
                )
            )
        else:
            await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancellation is a no-op: each request is a single stateless stream."""
        updater = TaskUpdater(
            event_queue,
            task_id=context.task_id,
            context_id=context.context_id,
        )
        await updater.cancel()
