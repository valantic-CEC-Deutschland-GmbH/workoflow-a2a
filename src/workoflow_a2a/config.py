"""Configuration for the Workoflow A2A server.

All settings are read from environment variables (optionally from a local
``.env`` file). Naming mirrors the conventions used by ``workoflow-mcp`` and
``workoflow-orchestrator``: ``WORKOFLOW_*`` for platform wiring, ``OTEL_*`` for
observability.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, loaded from the environment / ``.env``."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Platform (public Workoflow integration platform) ---
    # Used to resolve a personal access token -> (org, user, capabilities).
    workoflow_api_url: str = "http://host.docker.internal:3979"

    # --- Orchestrator (LAN-only ADK service) ---
    # The A2A server is the only public surface; it proxies to the private
    # orchestrator webhook over the internal network.
    orchestrator_url: str = "http://adk-orchestrator:8080"
    webhook_auth_token: str = ""
    orchestrator_timeout_seconds: float = 600.0

    # --- Public identity of this server (advertised in the agent card) ---
    public_base_url: str = "http://localhost:9008"
    agent_name: str = "Workoflow Bot"
    agent_version: str = "0.1.0"

    # --- Auth phase (pluggable identity seam) ---
    # phase 1 = personal token (bearer). phase 2/3 (oidc/ias) land later.
    auth_phase: str = "personal_token"

    # --- Observability (Phoenix / OTLP) ---
    otel_service_name: str = "workoflow-a2a"
    otel_exporter_otlp_endpoint: str | None = None

    # --- Error tracking (Sentry) ---
    # Opt-in via the presence of a DSN; otherwise ``setup_sentry()`` is a no-op.
    sentry_dsn: str = ""
    sentry_environment: str = "development"
    sentry_release: str | None = None
    sentry_traces_sample_rate: float = 0.0

    @property
    def workoflow_api_url_clean(self) -> str:
        return self.workoflow_api_url.rstrip("/")

    @property
    def orchestrator_url_clean(self) -> str:
        return self.orchestrator_url.rstrip("/")

    @property
    def public_base_url_clean(self) -> str:
        return self.public_base_url.rstrip("/")


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
