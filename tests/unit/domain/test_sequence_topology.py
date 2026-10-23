"""Reject impossible component conversations without rejecting return paths."""

from typing import Literal

import pytest

from domain.exceptions.sequence_errors import SequenceTopologyError
from domain.models.ast_steps import (
    AlternativeBranch,
    AltStep,
    LoopStep,
    MessageStep,
    OptStep,
    ScenarioStep,
)
from domain.models.edges import Edge
from domain.models.nodes import ClientNode, ComputeNode
from domain.models.protocols import ConnectionProtocol
from domain.models.roles import BusinessRole, ProjectRolesCatalog
from domain.models.sequence import ComponentLifeline, InteractionScenario
from domain.models.topology import ArchitectureGraph
from domain.specifications.interfaces import ValidationResult
from domain.specifications.sequence_validation import SequenceTopologyValidator

pytestmark = pytest.mark.unit


def _message(
    source: str = "browser",
    target: str = "handler",
    *,
    response: bool = False,
    delivery: Literal["sync", "async"] | None = "sync",
) -> MessageStep:
    return MessageStep(
        kind="message",
        from_lifeline=source,
        to_lifeline=target,
        action_name="Process order",
        message_kind="response" if response else "request",
        delivery_mode=delivery,
    )


def _validate(
    steps: list[ScenarioStep], *, asynchronous: bool = False, linked: bool = True
) -> ValidationResult:
    graph: ArchitectureGraph = ArchitectureGraph(
        nodes=[
            ClientNode(identifier="client"),
            ComputeNode(
                identifier="api",
                maximum_concurrency=4,
                maximum_queue_size=20,
                mean_processing_time_milliseconds=10,
                standard_deviation_processing_time=2,
                monthly_cost_usd=50,
            ),
        ],
        edges=[
            Edge(
                source_identifier="client",
                target_identifier="api",
                protocol=ConnectionProtocol(
                    name="test_protocol", is_asynchronous=asynchronous
                ),
            )
        ]
        if linked
        else [],
    )
    scenario: InteractionScenario = InteractionScenario(
        scenario_id="order",
        requirement_identifier="FR-order",
        description="Place order",
        lifelines=[
            ComponentLifeline(
                kind="component",
                lifeline_id=lifeline,
                architecture_node_id=node,
                display_name=node,
                description=node,
            )
            for lifeline, node in (("browser", "client"), ("handler", "api"))
        ],
        steps=steps,
    )
    return SequenceTopologyValidator().validate_scenario(
        scenario,
        ProjectRolesCatalog(
            roles=[BusinessRole(role_id="buyer", name="Buyer", description="Buyer")]
        ),
        graph,
        "FR-order",
    )


def test_request_and_reverse_response_need_only_one_directed_c4_link() -> None:
    result: ValidationResult = _validate(
        [_message(), _message("handler", "browser", response=True)]
    )
    assert result.is_successful


@pytest.mark.parametrize(
    ("asynchronous", "delivery"), [(False, "sync"), (True, "async")]
)
def test_message_uses_the_configured_link_mode(
    *, asynchronous: bool, delivery: Literal["sync", "async"]
) -> None:
    assert _validate(
        [_message(delivery=delivery)], asynchronous=asynchronous
    ).is_successful


@pytest.mark.parametrize("delivery", [None, "async"])
def test_missing_or_incompatible_delivery_is_rejected(
    delivery: Literal["async"] | None,
) -> None:
    result: ValidationResult = _validate([_message(delivery=delivery)])
    assert result.has_error(SequenceTopologyError)


def test_existing_components_do_not_imply_a_link() -> None:
    result: ValidationResult = _validate([_message()], linked=False)
    assert result.has_error(SequenceTopologyError)
    assert result.errors[0].affected_node_identifiers == ["client", "api"]


def test_reverse_request_is_not_a_response() -> None:
    result: ValidationResult = _validate([_message("handler", "browser")])
    assert result.has_error(SequenceTopologyError)


@pytest.mark.parametrize("delivery", ["sync", "async"])
def test_unsolicited_response_is_rejected(delivery: Literal["sync", "async"]) -> None:
    result: ValidationResult = _validate(
        [_message("handler", "browser", response=True, delivery=delivery)]
    )
    assert result.has_error(SequenceTopologyError)


def test_response_cannot_be_reused() -> None:
    reply: MessageStep = _message("handler", "browser", response=True)
    assert _validate([_message(), reply, reply]).has_error(SequenceTopologyError)


def test_request_in_another_alternative_does_not_authorize_response() -> None:
    steps: list[ScenarioStep] = [
        AltStep(
            kind="alt",
            branches=[
                AlternativeBranch(condition="create", steps=[_message()]),
                AlternativeBranch(
                    condition=None,
                    steps=[_message("handler", "browser", response=True)],
                ),
            ],
        )
    ]
    assert _validate(steps).has_error(SequenceTopologyError)


def test_each_branch_can_respond_to_a_request_before_the_branch() -> None:
    reply: MessageStep = _message("handler", "browser", response=True)
    branch: AltStep = AltStep(
        kind="alt",
        branches=[
            AlternativeBranch(condition="found", steps=[reply]),
            AlternativeBranch(condition=None, steps=[reply]),
        ],
    )
    assert _validate([_message(), branch]).is_successful


@pytest.mark.parametrize("kind", ["opt", "loop", "alt"])
def test_conditional_request_does_not_authorize_unconditional_response(
    kind: str,
) -> None:
    block: ScenarioStep
    if kind == "opt":
        block = OptStep(kind="opt", condition="create", steps=[_message()])
    elif kind == "loop":
        block = LoopStep(kind="loop", condition="retry", steps=[_message()])
    else:
        block = AltStep(
            kind="alt",
            branches=[
                AlternativeBranch(condition="a", steps=[_message()]),
                AlternativeBranch(condition="b", steps=[_message()]),
            ],
        )
    result: ValidationResult = _validate(
        [block, _message("handler", "browser", response=True)]
    )
    assert result.has_error(SequenceTopologyError)


def test_missing_link_inside_nested_loop_is_rejected() -> None:
    nested: OptStep = OptStep(
        kind="opt",
        condition="active",
        steps=[LoopStep(kind="loop", condition="retry", steps=[_message()])],
    )
    assert _validate([nested], linked=False).has_error(SequenceTopologyError)
