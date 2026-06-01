"""Agent card construction.

Two cards:

* **Public** (``/.well-known/agent-card.json``) - a single ``ask-workoflow``
  conversational skill, ``capabilities.streaming=True``, and a bearer security
  scheme. No org/user detail.
* **Authenticated extended** (``/agent/authenticatedExtendedCard``) - the public
  card plus per-user capability skills derived from the platform's
  ``/api/a2a/resolve`` ``capabilities`` list. Wired via ``extended_card_modifier``.
"""

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    HTTPAuthSecurityScheme,
    SecurityScheme,
)

from workoflow_a2a.config import Settings

ASK_SKILL_ID = "ask-workoflow"

DEFAULT_INPUT_MODES = ["text/plain"]
DEFAULT_OUTPUT_MODES = ["text/plain"]


def _ask_skill() -> AgentSkill:
    return AgentSkill(
        id=ASK_SKILL_ID,
        name="Ask Workoflow",
        description=(
            "Ask the Workoflow agent anything. It routes your request to your "
            "organization's enabled capabilities (people finder, web search, "
            "knowledge base, and more) and returns a single conversational answer."
        ),
        tags=["assistant", "conversational", "workoflow"],
        examples=[
            "Who in my company knows Kubernetes?",
            "Summarize our onboarding documentation.",
            "Search the web for the latest A2A protocol spec.",
        ],
    )


def build_public_card(settings: Settings) -> AgentCard:
    """Build the unauthenticated public agent card."""
    return AgentCard(
        name=settings.agent_name,
        description=(
            "Workoflow Bot - your organization's AI agent, exposed over the "
            "Agent2Agent (A2A) protocol. Authenticate with your Workoflow "
            "personal access token as a bearer credential."
        ),
        url=f"{settings.public_base_url_clean}/",
        version=settings.agent_version,
        capabilities=AgentCapabilities(streaming=True),
        default_input_modes=DEFAULT_INPUT_MODES,
        default_output_modes=DEFAULT_OUTPUT_MODES,
        skills=[_ask_skill()],
        security_schemes={
            "bearer": SecurityScheme(
                root=HTTPAuthSecurityScheme(
                    scheme="bearer",
                    description=(
                        "Workoflow personal access token (from /profile/). May "
                        "also be sent via the X-Prompt-Token header."
                    ),
                )
            )
        },
        security=[{"bearer": []}],
        supports_authenticated_extended_card=True,
    )


def skills_from_capabilities(capabilities: list[dict]) -> list[AgentSkill]:
    """Build per-capability A2A skills from the platform capability list.

    Each platform capability looks like
    ``{"type": "orchestrator.people_finder", "name": "People Finder", ...}``.
    """
    skills: list[AgentSkill] = []
    for cap in capabilities:
        cap_type = cap.get("type") or ""
        if not cap_type:
            continue
        name = cap.get("name") or cap_type
        skills.append(
            AgentSkill(
                id=cap_type,
                name=name,
                description=f"{name} capability, available to your Workoflow user.",
                tags=["capability", cap_type.split(".")[-1]],
            )
        )
    return skills


def build_extended_card(base_card: AgentCard, capabilities: list[dict]) -> AgentCard:
    """Return a copy of ``base_card`` with per-user capability skills appended."""
    extra = skills_from_capabilities(capabilities)
    if not extra:
        return base_card
    return base_card.model_copy(update={"skills": [*base_card.skills, *extra]})
