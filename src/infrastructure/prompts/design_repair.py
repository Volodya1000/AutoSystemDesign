"""Prompt builder for repair iterations of the design loop."""

from application.tasks import DesignTask
from infrastructure.llm.models import Message, MessageRole
from infrastructure.prompts.fragments_schema import (
    OUTPUT_HARD_RULES,
    STRUCTURED_OUTPUT_SYSTEM_PROMPT,
    render_allowed_connections,
    render_output_schema,
)


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
            _render_detected_problems(task),
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


def _render_detected_problems(task: DesignTask) -> str:
    entries: list[str] = [
        f"[{feedback.error_code}] {feedback.message}"
        for feedback in task.validation_feedback
    ]
    entries.extend(
        f"[{failure.error_type}] {failure.message} (at {failure.location})"
        for failure in task.parsing_failures
    )
    if not entries:
        return "No specific problems were reported; re-check the rules and correct the graph."
    lines: list[str] = ["Detected problems:"]
    lines.extend(f"{index}. {entry}" for index, entry in enumerate(entries, start=1))
    return "\n".join(lines)
