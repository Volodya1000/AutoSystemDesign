# Copyright (c) 2026 Volodya1000
"""Prompt builder for the initial architecture design request."""

from application.tasks import DesignTask
from infrastructure.llm.models import Message, MessageRole
from infrastructure.prompts.fragments_scenario import render_scenario_summary
from infrastructure.prompts.fragments_schema import (
    FEW_SHOT_GRAPH_JSON,
    OUTPUT_HARD_RULES,
    STRUCTURED_OUTPUT_SYSTEM_PROMPT,
    render_allowed_connections,
    render_output_schema,
)


def build_initial_messages(task: DesignTask) -> list[Message]:
    """Build the [SYSTEM, USER] message pair for the first design attempt."""
    user_content: str = "\n\n".join(
        [
            (
                "Design the topology of a distributed system for the scenario below. "
                "Return the architecture graph as a single JSON object."
            ),
            render_scenario_summary(task.scenario),
            render_output_schema(),
            render_allowed_connections(),
            f"Example of a correct answer:\n{FEW_SHOT_GRAPH_JSON}",
            OUTPUT_HARD_RULES,
        ]
    )
    messages: list[Message] = [
        Message(role=MessageRole.SYSTEM, content=STRUCTURED_OUTPUT_SYSTEM_PROMPT),
        Message(role=MessageRole.USER, content=user_content),
    ]
    return messages
