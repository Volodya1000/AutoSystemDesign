# Copyright (c) 2026 Volodya1000
from typing import Literal

import pytest
from pydantic import ValidationError

from domain.models.ast_steps import MessageStep
from domain.models.nodes import ClientNode, ComputeNode
from domain.models.roles import BusinessRole, ProjectRolesCatalog
from domain.models.sequence import (
    ComponentLifeline,
    InteractionScenario,
    UserLifeline,
)
from domain.models.topology import ArchitectureGraph
from domain.specifications.sequence_validator import (
    AsyncDeliveryModeError,
    ClientOwnershipValidator,
    DeliveryModeValidator,
    SequenceIntegrityValidator,
    SharedClientLifelineError,
)

pytestmark = pytest.mark.unit

_MessageKind = Literal["request", "response", "event", "notification", "user_action"]
_DeliveryMode = Literal["sync", "async"]


# ------------------------------------------------------------------ fixtures


def _catalog(*role_ids: str) -> ProjectRolesCatalog:
    return ProjectRolesCatalog(
        roles=[
            BusinessRole(role_id=rid, name=rid.title(), description=f"{rid} role")
            for rid in role_ids
        ]
    )


def _user(lifeline_id: str, role_id: str) -> UserLifeline:
    return UserLifeline(
        kind="user",
        lifeline_id=lifeline_id,
        business_role_id=role_id,
        scenario_role="initiator",
        description=f"{lifeline_id} as {role_id}",
    )


def _component(lifeline_id: str, node_id: str) -> ComponentLifeline:
    return ComponentLifeline(
        kind="component",
        lifeline_id=lifeline_id,
        architecture_node_id=node_id,
        display_name=lifeline_id,
        description=lifeline_id,
    )


def _graph_with_client_and_compute() -> ArchitectureGraph:
    return ArchitectureGraph(
        nodes=[
            ClientNode(identifier="web_client"),
            ComputeNode(
                identifier="backend",
                maximum_concurrency=100,
                maximum_queue_size=500,
                mean_processing_time_milliseconds=10.0,
                standard_deviation_processing_time=2.0,
                monthly_cost_usd=50.0,
            ),
        ],
        edges=[],
    )


def _message(
    sender: str,
    recipient: str,
    *,
    kind: _MessageKind = "request",
    delivery_mode: _DeliveryMode | None = "sync",
) -> MessageStep:
    return MessageStep(
        kind="message",
        from_lifeline=sender,
        to_lifeline=recipient,
        action_name="ping",
        message_kind=kind,
        delivery_mode=delivery_mode,
    )


# -------------------------------------------------------------- integrity


class TestSequenceIntegrityValidator:
    def test_catches_unknown_architecture_nodes(self) -> None:
        catalog = _catalog("buyer")
        graph = ArchitectureGraph(nodes=[ClientNode(identifier="web_client")], edges=[])
        lifeline = _component("l1", "non_existent_db")
        scenario = InteractionScenario(
            scenario_id="s1",
            requirement_identifier="req_1",
            description="desc",
            lifelines=[lifeline],
            steps=[
                MessageStep(
                    kind="message",
                    from_lifeline="l1",
                    to_lifeline="l1",
                    action_name="ping",
                    message_kind="event",
                    delivery_mode="async",
                )
            ],
        )

        result = SequenceIntegrityValidator().validate_scenario(
            scenario, catalog, graph, expected_requirement_id="req_1"
        )

        assert result.is_successful is False
        assert (
            "references unknown architecture_node_id 'non_existent_db'"
            in result.errors[0].message
        )


# ---------------------------------------------------------- client ownership


class TestClientOwnershipValidator:
    def test_shared_client_between_two_roles_is_rejected(self) -> None:
        graph = _graph_with_client_and_compute()
        catalog = _catalog("sender", "recipient")
        scenario = InteractionScenario(
            scenario_id="s1",
            requirement_identifier="req_1",
            description="shared client",
            lifelines=[
                _user("sender_1", "sender"),
                _user("recipient_1", "recipient"),
                _component("social_client", "web_client"),
            ],
            steps=[
                _message("sender_1", "social_client", kind="request"),
                _message(
                    "social_client",
                    "recipient_1",
                    kind="notification",
                    delivery_mode="async",
                ),
            ],
        )

        result = ClientOwnershipValidator().validate_scenario(
            scenario, catalog, graph, expected_requirement_id="req_1"
        )

        assert result.is_successful is False
        errors = [e for e in result.errors if isinstance(e, SharedClientLifelineError)]
        assert len(errors) == 1
        assert errors[0].client_lifeline_id == "social_client"
        assert errors[0].business_role_ids == ["recipient", "sender"]

    def test_client_used_by_one_role_is_accepted(self) -> None:
        graph = _graph_with_client_and_compute()
        catalog = _catalog("buyer")
        scenario = InteractionScenario(
            scenario_id="s1",
            requirement_identifier="req_1",
            description="single-role client",
            lifelines=[
                _user("buyer_1", "buyer"),
                _component("buyer_client", "web_client"),
            ],
            steps=[
                _message("buyer_1", "buyer_client", kind="request"),
                _message("buyer_client", "buyer_1", kind="response"),
            ],
        )

        result = ClientOwnershipValidator().validate_scenario(
            scenario, catalog, graph, expected_requirement_id="req_1"
        )

        assert result.is_successful is True

    def test_same_role_with_two_lifelines_of_one_client_is_accepted(self) -> None:
        """Two tabs of the same buyer are still one actor: no violation."""
        graph = _graph_with_client_and_compute()
        catalog = _catalog("buyer")
        scenario = InteractionScenario(
            scenario_id="s1",
            requirement_identifier="req_1",
            description="buyer with two tabs",
            lifelines=[
                _user("buyer_tab_1", "buyer"),
                _user("buyer_tab_2", "buyer"),
                _component("shared_browser", "web_client"),
            ],
            steps=[
                _message("buyer_tab_1", "shared_browser", kind="request"),
                _message(
                    "shared_browser",
                    "buyer_tab_2",
                    kind="notification",
                    delivery_mode="async",
                ),
            ],
        )

        result = ClientOwnershipValidator().validate_scenario(
            scenario, catalog, graph, expected_requirement_id="req_1"
        )

        assert result.is_successful is True


# ---------------------------------------------------------- delivery mode


class TestDeliveryModeValidator:
    def test_event_without_async_is_rejected(self) -> None:
        catalog = _catalog("buyer")
        graph = _graph_with_client_and_compute()
        scenario = InteractionScenario(
            scenario_id="s1",
            requirement_identifier="req_1",
            description="bad delivery mode",
            lifelines=[
                _user("buyer_1", "buyer"),
                _component("backend_api", "backend"),
            ],
            steps=[
                _message(
                    "buyer_1",
                    "backend_api",
                    kind="event",
                    delivery_mode="sync",
                )
            ],
        )

        result = DeliveryModeValidator().validate_scenario(
            scenario, catalog, graph, expected_requirement_id="req_1"
        )

        assert result.is_successful is False
        errors = [e for e in result.errors if isinstance(e, AsyncDeliveryModeError)]
        assert len(errors) == 1
        assert errors[0].message_kind == "event"

    def test_event_with_async_is_accepted(self) -> None:
        catalog = _catalog("buyer")
        graph = _graph_with_client_and_compute()
        scenario = InteractionScenario(
            scenario_id="s1",
            requirement_identifier="req_1",
            description="good delivery mode",
            lifelines=[
                _user("buyer_1", "buyer"),
                _component("backend_api", "backend"),
            ],
            steps=[
                _message(
                    "buyer_1",
                    "backend_api",
                    kind="event",
                    delivery_mode="async",
                )
            ],
        )

        result = DeliveryModeValidator().validate_scenario(
            scenario, catalog, graph, expected_requirement_id="req_1"
        )

        assert result.is_successful is True

    def test_request_without_async_is_accepted(self) -> None:
        """Sync request/response pairs are the normal case."""
        catalog = _catalog("buyer")
        graph = _graph_with_client_and_compute()
        scenario = InteractionScenario(
            scenario_id="s1",
            requirement_identifier="req_1",
            description="sync call",
            lifelines=[
                _user("buyer_1", "buyer"),
                _component("backend_api", "backend"),
            ],
            steps=[
                _message("buyer_1", "backend_api", kind="request"),
                _message("backend_api", "buyer_1", kind="response"),
            ],
        )

        result = DeliveryModeValidator().validate_scenario(
            scenario, catalog, graph, expected_requirement_id="req_1"
        )

        assert result.is_successful is True


# ------------------------------------------------------ unused lifelines


class TestUnusedLifelines:
    def test_declared_lifeline_without_messages_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="never participate"):
            InteractionScenario(
                scenario_id="s1",
                requirement_identifier="req_1",
                description="unused lifeline",
                lifelines=[
                    _user("buyer_1", "buyer"),
                    _component("ghost", "web_client"),
                ],
                steps=[_message("buyer_1", "buyer_1")],
            )

    def test_scenario_where_every_lifeline_participates_is_accepted(self) -> None:
        scenario = InteractionScenario(
            scenario_id="s1",
            requirement_identifier="req_1",
            description="all lifelines used",
            lifelines=[
                _user("buyer_1", "buyer"),
                _component("client", "web_client"),
            ],
            steps=[
                _message("buyer_1", "client", kind="request"),
                _message("client", "buyer_1", kind="response"),
            ],
        )

        assert len(scenario.lifelines) == 2
