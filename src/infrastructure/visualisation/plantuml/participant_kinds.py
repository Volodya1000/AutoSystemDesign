"""Deterministic mapping from C4 NodeType to PlantUML participant keyword.

Extracted from ``sequence_builder`` so the mapping table and its lookup
rules stay unit-testable in isolation and the builder keeps a single
responsibility (document assembly).

Rationale: the C4 model already carries each component's semantic role
(load balancer, database, message broker, ...).  Rendering that role as a
UML ``boundary`` / ``database`` / ``queue`` participant is a pure
translation step; the LLM never chooses a participant style, so no
prompt change is needed.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from domain.models.enums import NodeType
from domain.models.sequence import (
    ComponentLifeline,
    ScenarioLifeline,
    UserLifeline,
)

#: C4 NodeType -> PlantUML participant keyword.
NODE_TYPE_TO_PLANTUML_KEYWORD: Final[Mapping[NodeType, str]] = MappingProxyType({
    NodeType.CLIENT: "boundary",
    NodeType.LOAD_BALANCER: "boundary",
    NodeType.COMPUTE: "control",
    NodeType.DATABASE: "database",
    NodeType.CACHE: "collections",
    NodeType.MESSAGE_BROKER: "queue",
})

#: Fallback when the graph does not contain the referenced component or
#: when the subject was built without a graph (legacy call path).
DEFAULT_COMPONENT_KEYWORD: Final[str] = "participant"

#: A UserLifeline always renders as a real UML actor.
USER_LIFELINE_KEYWORD: Final[str] = "actor"


def participant_keyword(
    lifeline: ScenarioLifeline,
    node_type_by_id: dict[str, NodeType],
) -> str:
    """Return the PlantUML participant keyword for one lifeline.

    ``node_type_by_id`` may be empty: every component then falls back to
    ``DEFAULT_COMPONENT_KEYWORD`` so the diagram still renders when the
    graph is not available (or does not contain the referenced node).
    """
    if isinstance(lifeline, UserLifeline):
        return USER_LIFELINE_KEYWORD
    if isinstance(lifeline, ComponentLifeline):
        node_type = node_type_by_id.get(lifeline.architecture_node_id)
        if node_type is not None:
            return NODE_TYPE_TO_PLANTUML_KEYWORD.get(
                node_type, DEFAULT_COMPONENT_KEYWORD
            )
    return DEFAULT_COMPONENT_KEYWORD
