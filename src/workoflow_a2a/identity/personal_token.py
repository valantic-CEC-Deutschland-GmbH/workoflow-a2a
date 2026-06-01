"""Phase 1 resolver: forward a personal access token to the platform.

The card advertises an HTTP bearer scheme; the bearer value is the user's
Workoflow personal access token. We hand it to ``POST /api/a2a/resolve`` and
turn the response into a :class:`ResolvedIdentity`.
"""

from workoflow_a2a.identity.base import ResolvedIdentity
from workoflow_a2a.platform_client import PlatformClient, get_platform_client


class PersonalTokenResolver:
    """Resolve a personal access token via the platform resolve endpoint."""

    def __init__(self, platform_client: PlatformClient | None = None) -> None:
        self._client = platform_client or get_platform_client()

    async def resolve(self, token: str) -> ResolvedIdentity:
        data = await self._client.resolve(token)
        return ResolvedIdentity(
            org_uuid=data.get("org_uuid") or "",
            workflow_user_id=data.get("workflow_user_id") or "",
            email=data.get("email"),
            display_name=data.get("display_name"),
            capabilities=data.get("capabilities") or [],
        )
