"""Identity resolver protocol and the resolved-identity value object."""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ResolvedIdentity:
    """A Workoflow user resolved from an inbound A2A credential.

    This is exactly the identity tuple the orchestrator webhook needs, plus the
    capability list used to build the authenticated extended card.
    """

    org_uuid: str
    workflow_user_id: str
    email: str | None = None
    display_name: str | None = None
    # Each capability: {"type": str, "name": str, "instance_id": None, "instance_name": None}
    capabilities: list[dict] = field(default_factory=list)


@runtime_checkable
class IdentityResolver(Protocol):
    """Resolves an inbound credential (a bearer token) to a Workoflow user.

    Phase 1 forwards a personal access token to the platform. Later phases
    (OIDC authorization-code, SAP IAS App2App) implement the same protocol and
    are selected via ``Settings.auth_phase`` - the executor never changes.
    """

    async def resolve(self, token: str) -> ResolvedIdentity:
        """Resolve ``token`` to a :class:`ResolvedIdentity`.

        Raises :class:`workoflow_a2a.platform_client.PlatformAuthError` (or a
        subclass) when the credential is invalid, so the executor can map it to
        an A2A ``requires_auth`` task state.
        """
        ...
