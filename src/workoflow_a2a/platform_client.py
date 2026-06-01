"""HTTP client for the Workoflow integration platform.

Mirrors ``workoflow-mcp``'s ``client.py``: a lazily-initialised, singleton
``httpx.AsyncClient`` with no persistent auth (the per-call token is forwarded
as ``X-Prompt-Token``). The only call this server makes is ``/api/a2a/resolve``,
which maps a personal access token to the calling user's identity + capabilities.
"""

import httpx

from workoflow_a2a.config import get_settings


class PlatformAuthError(Exception):
    """Raised when the platform rejects the token (HTTP 401)."""


class PlatformClient:
    """Async HTTP client for the platform ``/api/a2a`` surface."""

    def __init__(self, base_url: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.workoflow_api_url).rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def resolve(self, prompt_token: str) -> dict:
        """Resolve a personal access token to identity + capabilities.

        Returns the platform payload:
        ``{org_uuid, workflow_user_id, email, display_name, capabilities[]}``.

        Raises ``PlatformAuthError`` on HTTP 401 (bad/missing token).
        """
        client = await self._get_client()
        headers = {
            "X-Prompt-Token": prompt_token,
            "Accept": "application/json",
        }
        response = await client.post(
            f"{self.base_url}/api/a2a/resolve",
            headers=headers,
        )
        if response.status_code == 401:
            raise PlatformAuthError("Platform rejected the personal access token")
        response.raise_for_status()
        return response.json()


_client: PlatformClient | None = None


def get_platform_client() -> PlatformClient:
    """Return the singleton ``PlatformClient`` instance."""
    global _client
    if _client is None:
        _client = PlatformClient()
    return _client
