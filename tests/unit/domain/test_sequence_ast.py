# Copyright (c) 2026 Volodya1000
import pytest
from pydantic import ValidationError

from domain.models.ast_steps import AlternativeBranch, AltStep, MessageStep
from domain.models.sequence import InteractionScenario, UserLifeline

pytestmark = pytest.mark.unit


def test_altstep_requires_else_branch_to_be_last() -> None:
    """Require the else branch to be last when condition=None."""
    msg = MessageStep(
        kind="message",
        from_lifeline="a",
        to_lifeline="b",
        action_name="x",
        message_kind="event",
    )

    with pytest.raises(
        ValidationError, match=r"The default branch .* must be the last one"
    ):
        AltStep(
            kind="alt",
            branches=[
                AlternativeBranch(
                    condition=None, steps=[msg]
                ),  # Invalid: 'else' is first
                AlternativeBranch(condition="is_true", steps=[msg]),
            ],
        )


def test_interaction_scenario_catches_unknown_lifelines_in_messages() -> None:
    """Ensures from_lifeline and to_lifeline exist in the lifelines array."""
    lifeline = UserLifeline(
        kind="user",
        lifeline_id="user_1",
        business_role_id="r1",
        scenario_role="r",
        description="d",
    )

    with pytest.raises(
        ValidationError, match="Unknown message recipient: 'unknown_server'"
    ):
        InteractionScenario(
            scenario_id="s1",
            requirement_identifier="req_1",
            description="desc",
            lifelines=[lifeline],
            steps=[
                MessageStep(
                    kind="message",
                    from_lifeline="user_1",
                    to_lifeline="unknown_server",
                    action_name="ping",
                    message_kind="request",
                )
            ],
        )
