"""Prompt builder for repair iterations of the design loop."""

from application.tasks import DesignTask
from infrastructure.llm.models import Message, MessageRole
from infrastructure.prompts._feedback import render_feedback
from infrastructure.prompts.fragments_schema import (
    OUTPUT_HARD_RULES,
    STRUCTURED_OUTPUT_SYSTEM_PROMPT,
    render_allowed_connections,
    render_output_schema,
)

_EMPTY_FEEDBACK_MESSAGE: str = "No problems reported; re-check the rules."


def build_repair_messages(task: DesignTask) -> list[Message]:
    """Builds the [SYSTEM, USER] message pair for a repair attempt.

    The schema and the connection whitelist are repeated: small models
    forget them between turns.
    """
    user_content: str = "\n\n".join(
        [
            (
                "Your previous answer for the architecture graph is not valid. "
                "Fix ALL the problems listed below and return the complete "
                "corrected JSON object."
            ),
            f"Previous answer:\n{task.previous_graph_payload or ''}",
            render_feedback(
                task.validation_feedback,
                task.parsing_failures,
                empty_message=_EMPTY_FEEDBACK_MESSAGE,
            ),
            render_output_schema(),
            render_allowed_connections(),
            OUTPUT_HARD_RULES,
        ]
    )
    messages: list[Message] = [
        Message(role=MessageRole.SYSTEM, content=STRUCTURED_OUTPUT_SYSTEM_PROMPT),
        Message(role=MessageRole.USER, content=user_content),
    ]
    return messages
