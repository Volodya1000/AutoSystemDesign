"""Sequence-diagram parsers (roles catalog and interaction scenario)."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from domain.models.roles import ProjectRolesCatalog
from domain.models.sequence import InteractionScenario
from infrastructure.design._parsing import parse_payload
from infrastructure.design.sequence_normalization import normalize_interaction_payload

if TYPE_CHECKING:
    from application.usage import TokenUsage
    from domain.models.topology import ArchitectureGraph


def parse_roles_catalog(payload: str, usage: TokenUsage) -> ProjectRolesCatalog:
    """Parse a raw LLM completion into a ProjectRolesCatalog."""
    return parse_payload(payload, ProjectRolesCatalog, usage)


def parse_interaction_scenario(
    payload: str,
    usage: TokenUsage,
    *,
    architecture_graph: ArchitectureGraph | None = None,
) -> InteractionScenario:
    """Parse and validate an interaction scenario against its optional C4 graph."""
    normalizer = (
        None
        if architecture_graph is None
        else partial(normalize_interaction_payload, graph=architecture_graph)
    )
    return parse_payload(payload, InteractionScenario, usage, normalizer=normalizer)
