"""Sequence-diagram parsers (roles catalog and interaction scenario)."""

from __future__ import annotations

from application.usage import TokenUsage
from domain.models.roles import ProjectRolesCatalog
from domain.models.sequence import InteractionScenario
from infrastructure.design._parsing import parse_payload


def parse_roles_catalog(payload: str, usage: TokenUsage) -> ProjectRolesCatalog:
    """Parses a raw LLM completion into a ProjectRolesCatalog."""
    return parse_payload(payload, ProjectRolesCatalog, usage)


def parse_interaction_scenario(payload: str, usage: TokenUsage) -> InteractionScenario:
    """Parses a raw LLM completion into an InteractionScenario."""
    return parse_payload(payload, InteractionScenario, usage)
