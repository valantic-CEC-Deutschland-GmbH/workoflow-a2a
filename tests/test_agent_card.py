"""M5: public vs extended agent card."""

from workoflow_a2a.agent_card import (
    ASK_SKILL_ID,
    build_extended_card,
    build_public_card,
    skills_from_capabilities,
)
from workoflow_a2a.config import Settings


def _settings() -> Settings:
    return Settings(
        public_base_url="https://a2a.example.com",
        agent_name="Workoflow Bot",
        agent_version="9.9.9",
    )


def test_public_card_has_single_ask_skill_and_bearer_scheme():
    card = build_public_card(_settings())
    assert card.name == "Workoflow Bot"
    assert card.url == "https://a2a.example.com/"
    assert card.version == "9.9.9"
    assert card.capabilities.streaming is True
    assert card.supports_authenticated_extended_card is True
    assert [s.id for s in card.skills] == [ASK_SKILL_ID]
    assert "bearer" in (card.security_schemes or {})
    # No org/user detail leaks into the public card.
    assert "people" not in card.description.lower()


def test_skills_from_capabilities_maps_type_and_name():
    caps = [
        {"type": "orchestrator.people_finder", "name": "People Finder"},
        {"type": "orchestrator.web_agent", "name": "Web Agent"},
        {"type": "", "name": "ignored"},  # no type -> skipped
    ]
    skills = skills_from_capabilities(caps)
    assert [s.id for s in skills] == [
        "orchestrator.people_finder",
        "orchestrator.web_agent",
    ]
    assert skills[0].name == "People Finder"
    assert "people_finder" in skills[0].tags


def test_extended_card_appends_capability_skills():
    base = build_public_card(_settings())
    caps = [{"type": "orchestrator.knowledge_base", "name": "Knowledge Base"}]
    extended = build_extended_card(base, caps)
    ids = [s.id for s in extended.skills]
    assert ids == [ASK_SKILL_ID, "orchestrator.knowledge_base"]
    # Base card is not mutated.
    assert [s.id for s in base.skills] == [ASK_SKILL_ID]


def test_extended_card_without_capabilities_returns_base():
    base = build_public_card(_settings())
    assert build_extended_card(base, []) is base
