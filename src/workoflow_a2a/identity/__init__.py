"""Pluggable identity resolution.

The executor depends only on the :class:`IdentityResolver` protocol and the
:class:`ResolvedIdentity` dataclass. Switching auth phases (personal token ->
OIDC -> SAP IAS) is a DI + agent-card ``security_schemes`` change, never an
executor change.
"""

from workoflow_a2a.identity.base import IdentityResolver, ResolvedIdentity
from workoflow_a2a.identity.personal_token import PersonalTokenResolver

__all__ = ["IdentityResolver", "ResolvedIdentity", "PersonalTokenResolver", "get_resolver"]


def get_resolver() -> IdentityResolver:
    """Return the resolver for the configured auth phase.

    Phase 1 (``personal_token``) is the only implemented phase; ``oidc`` and
    ``ias`` raise until their resolvers land (see the build plan, M7).
    """
    from workoflow_a2a.config import get_settings

    phase = get_settings().auth_phase
    if phase == "personal_token":
        return PersonalTokenResolver()
    raise NotImplementedError(
        f"auth_phase={phase!r} is not implemented yet (only 'personal_token')"
    )
