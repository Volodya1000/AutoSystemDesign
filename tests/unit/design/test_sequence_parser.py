# Copyright (c) 2026 Volodya1000
"""Regression tests for reconciling sequence lifelines with C4 nodes."""

import json
from itertools import starmap

import pytest

from application.exceptions.generation_exceptions import DesignProposalParsingError
from application.usage import TokenUsage
from domain.models.ast_steps import MessageStep
from domain.models.enums import NodeType
from domain.models.topology import ArchitectureGraph
from infrastructure.design.sequence_parser import parse_interaction_scenario
from tests.factories import create_test_node

pytestmark = pytest.mark.unit

USAGE: TokenUsage = TokenUsage(prompt_tokens=11, completion_tokens=7)


def _component_lifeline(lifeline_id: str, node_id: str) -> dict[str, str]:
    return {
        "kind": "component",
        "lifeline_id": lifeline_id,
        "architecture_node_id": node_id,
        "display_name": lifeline_id,
        "description": "Component used by the interaction.",
    }


def _message(sender: str, recipient: str) -> dict[str, object]:
    return {
        "kind": "message",
        "from_lifeline": sender,
        "to_lifeline": recipient,
        "action_name": "persist_order",
        "message_kind": "request",
        "delivery_mode": "sync",
    }


def _payload(lifelines: list[dict[str, str]], steps: list[dict[str, object]]) -> str:
    return json.dumps(
        {
            "scenario_id": "checkout",
            "requirement_identifier": "FR-004",
            "description": "Create an order after successful payment.",
            "lifelines": lifelines,
            "steps": steps,
        }
    )


def _graph(*node_ids: tuple[str, NodeType]) -> ArchitectureGraph:
    return ArchitectureGraph(
        nodes=list(starmap(create_test_node, node_ids)),
        edges=[],
    )


class TestParseInteractionScenario:
    def test_adds_missing_backend_lifeline_used_in_nested_steps(self) -> None:
        payload = _payload(
            lifelines=[_component_lifeline("orders_api", "orders_api")],
            steps=[
                {
                    "kind": "alt",
                    "branches": [
                        {
                            "condition": "payment succeeded",
                            "steps": [_message("orders_api", "orders_db")],
                        },
                        {
                            "condition": None,
                            "steps": [_message("orders_api", "orders_db")],
                        },
                    ],
                }
            ],
        )

        scenario = parse_interaction_scenario(
            payload,
            usage=USAGE,
            architecture_graph=_graph(
                ("orders_api", NodeType.COMPUTE),
                ("orders_db", NodeType.DATABASE),
            ),
        )

        assert {lifeline.lifeline_id for lifeline in scenario.lifelines} == {
            "orders_api",
            "orders_db",
        }

    def test_maps_c4_reference_to_its_unique_declared_lifeline(self) -> None:
        payload = _payload(
            lifelines=[
                _component_lifeline("orders_api", "orders_api"),
                _component_lifeline("database", "orders_db"),
            ],
            steps=[_message("orders_api", "orders_db")],
        )

        scenario = parse_interaction_scenario(
            payload,
            usage=USAGE,
            architecture_graph=_graph(
                ("orders_api", NodeType.COMPUTE),
                ("orders_db", NodeType.DATABASE),
            ),
        )

        step = scenario.steps[0]
        assert isinstance(step, MessageStep)
        assert step.to_lifeline == "database"

    def test_rejects_ambiguous_mapping_to_multiple_lifelines(self) -> None:
        payload = _payload(
            lifelines=[
                _component_lifeline("orders_api", "orders_api"),
                _component_lifeline("primary_db", "orders_db"),
                _component_lifeline("replica_db", "orders_db"),
            ],
            steps=[
                _message("orders_api", "orders_db"),
                _message("primary_db", "orders_api"),
                _message("replica_db", "orders_api"),
            ],
        )

        with pytest.raises(DesignProposalParsingError) as exc_info:
            parse_interaction_scenario(
                payload,
                usage=USAGE,
                architecture_graph=_graph(
                    ("orders_api", NodeType.COMPUTE),
                    ("orders_db", NodeType.DATABASE),
                ),
            )

        assert exc_info.value.failure_details

    def test_does_not_infer_a_missing_client_lifeline(self) -> None:
        payload = _payload(
            lifelines=[_component_lifeline("orders_api", "orders_api")],
            steps=[_message("orders_api", "web_client")],
        )

        with pytest.raises(DesignProposalParsingError) as exc_info:
            parse_interaction_scenario(
                payload,
                usage=USAGE,
                architecture_graph=_graph(
                    ("orders_api", NodeType.COMPUTE),
                    ("web_client", NodeType.CLIENT),
                ),
            )

        assert exc_info.value.failure_details
