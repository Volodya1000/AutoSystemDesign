"""Typed interaction fixtures for API and traceability tests."""

from domain.models.ast_steps import MessageStep
from domain.models.sequence import ComponentLifeline, InteractionScenario


def create_test_interaction(
    requirement_id: str, identifier: str
) -> InteractionScenario:
    """Build an interaction with a local processing step."""
    return InteractionScenario(
        scenario_id=identifier,
        requirement_identifier=requirement_id,
        description="Process order",
        lifelines=[
            ComponentLifeline(
                kind="component",
                lifeline_id="api",
                architecture_node_id="api",
                display_name="Orders",
                description="Orders handler",
            )
        ],
        steps=[
            MessageStep(
                kind="message",
                from_lifeline="api",
                to_lifeline="api",
                action_name="Process",
                message_kind="request",
                delivery_mode="sync",
            )
        ],
    )
