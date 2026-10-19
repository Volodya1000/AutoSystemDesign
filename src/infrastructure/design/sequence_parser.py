"""Sequence-diagram parsers (roles catalog and interaction scenario)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.models.roles import ProjectRolesCatalog
from domain.models.sequence import InteractionScenario
from infrastructure.design._parsing import parse_payload

if TYPE_CHECKING:
    from application.usage import TokenUsage


def parse_roles_catalog(payload: str, usage: TokenUsage) -> ProjectRolesCatalog:
    """Parse a raw LLM completion into a ProjectRolesCatalog."""
    return parse_payload(payload, ProjectRolesCatalog, usage)


def parse_interaction_scenario(payload: str, usage: TokenUsage) -> InteractionScenario:
    """Parse a raw LLM completion into an InteractionScenario."""
    return parse_payload(payload, InteractionScenario, usage)
