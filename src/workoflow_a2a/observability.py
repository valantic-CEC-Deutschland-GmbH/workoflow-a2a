"""OpenTelemetry + Sentry setup, mirroring ``workoflow-mcp`` /
``workoflow-orchestrator``.

Both integrations are opt-in via the presence of an env var (an OTLP endpoint
for tracing, a DSN for Sentry). Imports are lazy so the package works without
the optional extras installed; a missing package logs a warning and is a no-op.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from workoflow_a2a.config import get_settings

if TYPE_CHECKING:
    from sentry_sdk.types import Event, Hint

logger = logging.getLogger(__name__)


def init_tracing() -> None:
    """Initialise OTLP tracing if an endpoint is configured."""
    settings = get_settings()
    endpoint = settings.otel_exporter_otlp_endpoint
    if not endpoint:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": settings.otel_service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces")
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        logger.info("OpenTelemetry tracing enabled, exporting to %s", endpoint)
    except ImportError:
        logger.warning("OpenTelemetry packages not installed, tracing disabled")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to initialize OpenTelemetry: %s", exc)


def _before_send(event: Event, hint: Hint) -> Event | None:
    """Drop events below error level as a safety net.

    The LoggingIntegration already filters by event_level, but this catches
    edge cases from other integrations or direct capture calls.
    """
    level = event.get("level")
    if level in ("info", "debug", "warning"):
        return None
    return event


def setup_sentry() -> None:
    """Initialise Sentry error tracking if a DSN is configured.

    The Starlette integration auto-instruments the ASGI app, so this only needs
    to run before the app is constructed (no manual middleware wiring).
    """
    settings = get_settings()
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.sentry_environment,
            release=settings.sentry_release or None,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            send_default_pii=False,
            integrations=[
                LoggingIntegration(
                    level=logging.WARNING,  # breadcrumbs from WARNING+ only
                    event_level=logging.ERROR,  # only ERROR+ creates Sentry issues
                ),
            ],
            before_send=_before_send,
        )
        logger.info(
            "Sentry error tracking enabled (environment=%s)",
            settings.sentry_environment,
        )
    except ImportError:
        logger.warning("sentry-sdk not installed, error tracking disabled")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to initialize Sentry: %s", exc)
