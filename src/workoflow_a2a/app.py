"""ASGI entrypoint: the A2A Starlette application.

Run with: ``uvicorn workoflow_a2a.app:app --host 0.0.0.0 --port 9000``.

Serves:
* ``GET /.well-known/agent-card.json`` (and legacy ``/.well-known/agent.json``)
  - public discovery, unauthenticated.
* ``POST /``                            - JSON-RPC ``message/send`` and
  ``message/stream``, authenticated by the card's bearer scheme.
* ``GET /agent/authenticatedExtendedCard`` - per-user skills (token required).
"""

import logging

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard

from workoflow_a2a.agent_card import build_extended_card, build_public_card
from workoflow_a2a.config import get_settings
from workoflow_a2a.executor import _extract_token
from workoflow_a2a.identity import get_resolver
from workoflow_a2a.observability import init_tracing, setup_sentry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_settings = get_settings()
init_tracing()
setup_sentry()

_public_card = build_public_card(_settings)


async def _extended_card_modifier(base_card: AgentCard, context) -> AgentCard:
    """Append per-user capability skills after resolving the caller's token.

    No / invalid token -> return the base card unchanged (the SDK still requires
    auth to reach this route; we simply don't enrich).
    """
    headers: dict[str, str] = {}
    if context is not None and getattr(context, "state", None):
        headers = context.state.get("headers", {}) or {}
    token = _extract_token(headers)
    if not token:
        return base_card
    try:
        identity = await get_resolver().resolve(token)
    except Exception:  # noqa: BLE001 - never break discovery on resolve failure
        logger.warning("Extended card: token resolution failed; serving base card")
        return base_card
    return build_extended_card(base_card, identity.capabilities)


def build_app():
    """Construct the A2A Starlette ASGI application."""
    executor = _build_executor()
    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
    )
    a2a_app = A2AStarletteApplication(
        agent_card=_public_card,
        http_handler=handler,
        extended_card_modifier=_extended_card_modifier,
    )
    return a2a_app.build()


def _build_executor():
    # Imported lazily so importing the card / app in tests does not require the
    # full executor dependency graph.
    from workoflow_a2a.executor import WorkoflowAgentExecutor

    return WorkoflowAgentExecutor()


app = build_app()
