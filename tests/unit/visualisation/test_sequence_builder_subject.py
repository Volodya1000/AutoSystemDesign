"""End-to-end checks of SequenceDiagramBuilder with SequenceDiagramSubject.

Covers:
* components get their C4 NodeType mapped to a specific PlantUML keyword
  (``boundary`` / ``control`` / ``database`` / ...) when the subject carries
  an architecture graph;
* the legacy call path (a bare ``InteractionScenario`` without a graph)
  still renders every component as a plain ``participant``;
* ``UserLifeline`` always renders as an ``actor`` regardless of the graph.
"""

from __future__ import annotations

import pytest

from application.pipeline.diagram_subjects import SequenceDiagramSubject
from domain.models.ast_steps import MessageStep, ScenarioStep
from domain.models.enums import NodeType
from domain.models.sequence import (
    ComponentLifeline,
    InteractionScenario,
    UserLifeline,
)
from domain.models.topology import ArchitectureGraph
from infrastructure.visualisation.plantuml.sequence_builder import (
    SequenceDiagramBuilder,
)
from tests.unit.test_structural_validator import create_test_node

pytestmark = pytest.mark.unit


def _user() -> UserLifeline:
    return UserLifeline(
        kind="user",
        lifeline_id="buyer_1",
        business_role_id="buyer",
        scenario_role="initiator",
        description="Customer",
    )


def _component(lifeline_id: str, node_id: str, display: str) -> ComponentLifeline:
    return ComponentLifeline(
        kind="component",
        lifeline_id=lifeline_id,
        architecture_node_id=node_id,
        display_name=display,
        description=display,
    )


def _scenario(lifelines: list) -> InteractionScenario:
    """Builds a scenario in which every lifeline participates in a message.

    Chained messages ensure no lifeline is left unused, satisfying the
    model-level invariant in ``InteractionScenario.validate_scenario_integrity``.
    """
    steps: list[ScenarioStep] = []
    if len(lifelines) == 1:
        steps.append(
            MessageStep(
                kind="message",
                from_lifeline=lifelines[0].lifeline_id,
                to_lifeline=lifelines[0].lifeline_id,
                action_name="POST /orders",
                message_kind="request",
                delivery_mode="sync",
            )
        )
    else:
        steps.extend(
            MessageStep(
                kind="message",
                from_lifeline=lifelines[index].lifeline_id,
                to_lifeline=lifelines[index + 1].lifeline_id,
                action_name="POST /orders",
                message_kind="request",
                delivery_mode="sync",
            )
            for index in range(len(lifelines) - 1)
        )
    return InteractionScenario(
        scenario_id="s1",
        requirement_identifier="REQ-1",
        description="Checkout",
        lifelines=list(lifelines),
        steps=steps,
    )


def test_subject_renders_mapped_keywords_for_components() -> None:
    """Every component is rendered with the keyword of its C4 NodeType."""
    lifelines = [
        _user(),
        _component("lb", "edge_lb", "Edge LB"),
        _component("api", "orders_api", "Orders API"),
        _component("db", "orders_db", "Orders DB"),
    ]
    graph = ArchitectureGraph(
        nodes=[
            create_test_node("edge_lb", NodeType.LOAD_BALANCER),
            create_test_node("orders_api", NodeType.COMPUTE),
            create_test_node("orders_db", NodeType.DATABASE),
        ],
        edges=[],
    )

    source = SequenceDiagramBuilder().build(
        SequenceDiagramSubject(
            scenario=_scenario(lifelines),
            architecture_graph=graph,
        )
    )

    assert 'actor "initiator' in source
    assert 'boundary "Edge LB" as lb' in source
    assert 'control "Orders API" as api' in source
    assert 'database "Orders DB" as db' in source


def test_bare_scenario_uses_participant_for_all_components() -> None:
    """Legacy call path: no graph supplied, components fall back to participant."""
    lifelines = [
        _user(),
        _component("api", "orders_api", "Orders API"),
    ]

    source = SequenceDiagramBuilder().build(_scenario(lifelines))

    assert 'actor "initiator' in source
    assert 'participant "Orders API" as api' in source


def test_component_missing_from_graph_falls_back_to_participant() -> None:
    """A component referencing an unknown C4 node must not crash the renderer."""
    lifelines = [
        _user(),
        _component("ghost", "not_in_graph", "Ghost"),
    ]
    graph = ArchitectureGraph(
        nodes=[create_test_node("orders_api", NodeType.COMPUTE)],
        edges=[],
    )

    source = SequenceDiagramBuilder().build(
        SequenceDiagramSubject(
            scenario=_scenario(lifelines),
            architecture_graph=graph,
        )
    )

    assert 'participant "Ghost" as ghost' in source


def test_user_lifeline_ignores_graph_mapping() -> None:
    """UserLifeline always renders as actor, even if a same-named node exists."""
    lifelines = [_user()]
    graph = ArchitectureGraph(
        nodes=[create_test_node("buyer", NodeType.COMPUTE)],
        edges=[],
    )

    source = SequenceDiagramBuilder().build(
        SequenceDiagramSubject(
            scenario=_scenario(lifelines),
            architecture_graph=graph,
        )
    )

    assert 'actor "initiator' in source
    assert "as buyer_1" in source


def test_all_node_types_map_to_expected_keywords() -> None:
    """Every NodeType in the mapping table produces its expected keyword."""
    cases = [
        (NodeType.LOAD_BALANCER, "boundary"),
        (NodeType.COMPUTE, "control"),
        (NodeType.DATABASE, "database"),
        (NodeType.CACHE, "collections"),
        (NodeType.MESSAGE_BROKER, "queue"),
    ]
    for index, (node_type, expected_keyword) in enumerate(cases):
        lifeline = _component(f"c{index}", f"node{index}", f"Comp{index}")
        graph = ArchitectureGraph(
            nodes=[create_test_node(f"node{index}", node_type)],
            edges=[],
        )
        scenario = _scenario([lifeline])
        source = SequenceDiagramBuilder().build(
            SequenceDiagramSubject(
                scenario=scenario,
                architecture_graph=graph,
            )
        )
        assert f'{expected_keyword} "Comp{index}" as c{index}' in source, (
            f"{node_type.value} should render as {expected_keyword}"
        )


def test_long_message_labels_are_wrapped_at_word_boundaries() -> None:
    lifelines = [_user(), _component("api", "orders_api", "Orders API")]
    scenario = _scenario(lifelines)
    scenario.steps = [
        MessageStep(
            kind="message",
            from_lifeline="buyer_1",
            to_lifeline="api",
            action_name=(
                "Validate customer credentials and "
                "retrieve account permissions"
            ),
            message_kind="request",
            delivery_mode="sync",
            description="Return the authorization result to the requesting client",
        )
    ]

    source = SequenceDiagramBuilder().build(scenario)

    assert r"\n" in source
    message_label = next(
        line.split(": ", maxsplit=1)[1]
        for line in source.splitlines()
        if "Validate customer" in line
    )
    assert all(len(line) <= 36 for line in message_label.split(r"\n"))


def test_long_diagram_title_is_wrapped_at_word_boundaries() -> None:
    scenario = _scenario([_user()])

    source = SequenceDiagramBuilder().build(
        scenario,
        title="Customer submits order and waits for payment confirmation",
    )

    assert (
        r"title Customer submits order and waits for\n"
        r"payment confirmation"
    ) in source


def test_short_labels_are_not_wrapped() -> None:
    source = SequenceDiagramBuilder().build(
        _scenario([_user(), _component("api", "orders_api", "Orders API")])
    )

    assert r": POST /orders" in source
