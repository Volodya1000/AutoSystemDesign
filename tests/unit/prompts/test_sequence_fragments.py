import pytest

from infrastructure.prompts.sequence_fragments import render_interaction_schema

pytestmark = pytest.mark.unit


def test_interaction_prompt_builds_lifelines_from_message_participants() -> None:
    prompt: str = render_interaction_schema()

    assert "first define the complete message steps" in prompt
    assert "build the 'lifelines' array from those participants only" in prompt
    assert "Do not add a lifeline just because a component exists" in prompt
    assert "including nested 'alt' branches" in prompt
    assert "Remove any unused lifeline" in prompt
