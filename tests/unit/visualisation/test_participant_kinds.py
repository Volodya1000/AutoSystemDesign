"""Unit tests of the C4 NodeType -> PlantUML participant keyword mapping."""

from __future__ import annotations

import pytest

from domain.models.enums import NodeType
from domain.models.sequence import ComponentLifeline, UserLifeline
from infrastructure.visualisation.plantuml.participant_kinds import (
    DEFAULT_COMPONENT_KEYWORD,
    NODE_TYPE_TO_PLANTUML_KEYWORD,
    participant_keyword,
)

pytestmark = pytest.mark.unit


def _component(node_id: str) -> ComponentLifeline:
    return ComponentLifeline(
        kind="component",
        lifeline_id="l1",
        architecture_node_id=node_id,
        display_name="d",
        description="d",
    )


@pytest.mark.parametrize(
    "node_type,expected",
    [
        (NodeType.CLIENT, "boundary"),
        (NodeType.LOAD_BALANCER, "boundary"),
        (NodeType.COMPUTE, "control"),
        (NodeType.DATABASE, "database"),
        (NodeType.CACHE, "collections"),
        (NodeType.MESSAGE_BROKER, "queue"),
    ],
)
def test_every_node_type_has_a_mapped_keyword(
    node_type: NodeType, expected: str
) -> None:
    assert NODE_TYPE_TO_PLANTUML_KEYWORD[node_type] == expected
    assert participant_keyword(_component("svc"), {"svc": node_type}) == expected


def test_user_lifeline_is_always_actor() -> None:
    lifeline = UserLifeline(
        kind="user",
        lifeline_id="u1",
        business_role_id="buyer",
        scenario_role="initiator",
        description="d",
    )
    assert participant_keyword(lifeline, {"buyer": NodeType.COMPUTE}) == "actor"


def test_missing_component_in_graph_falls_back() -> None:
    assert participant_keyword(_component("absent"), {}) == DEFAULT_COMPONENT_KEYWORD


def test_empty_graph_falls_back_to_participant() -> None:
    assert participant_keyword(_component("svc"), {}) == DEFAULT_COMPONENT_KEYWORD
