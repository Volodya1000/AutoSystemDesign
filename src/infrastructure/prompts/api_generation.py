"""Prompt builder for REST API Design generation and repair cycles."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from domain.models.api import ApiDesign
from domain.models.sequence import InteractionScenario, MessageStep
from infrastructure.llm.models import Message, MessageRole
from infrastructure.prompts._c4_context import render_c4_components
from infrastructure.prompts._feedback import render_feedback
from infrastructure.prompts.fragments_scenario import render_scenario_summary

if TYPE_CHECKING:
    from application.tasks import ApiDesignTask

API_DESIGN_SYSTEM_PROMPT: str = (
    "You are a principal software architect designing RESTful APIs "
    "(OpenAPI 3.1 compatible). Your objective is to design the public and "
    "service API endpoints required to satisfy the functional requirements "
    "and sequence interactions of the system.\n\n"
    "CRITICAL CONSTRAINTS:\n"
    "1. You MUST respond with EXACTLY ONE valid JSON object matching the "
    "ApiDesign schema.\n"
    "2. No markdown wrappers (do NOT use ```json fences), no commentary, "
    "no thinking text.\n"
    "3. Every operation MUST reference an existing "
    "'entrypoint_component_id' and 'handler_component_id' from the C4 graph.\n"
    "4. All URL path parameters like '{id}' MUST be declared in the "
    "operation's 'parameters' with in='path'.\n"
    "5. Every 'schema_ref' in request_body or responses MUST be defined "
    "in the root 'schemas' dictionary."
)

_EMPTY_FEEDBACK_MESSAGE: str = "No problems reported; re-check the schema."

_C4_HEADING: str = "Available C4 Architecture Components:"


def _render_sequence_context(sequences: list[InteractionScenario]) -> str:
    """Summarizes sequence diagram interactions to guide endpoint and payload design."""
    lines: list[str] = ["Sequence Diagram Scenarios (User & Service interactions):"]
    for seq in sequences:
        lines.append(
            f"\n- Scenario: {seq.scenario_id} "
            f"(Requirement: {seq.requirement_identifier})"
        )
        lines.append(f"  Description: {seq.description}")
        lines.append("  Interaction steps:")
        for step in seq.steps:
            if isinstance(step, MessageStep):
                mode = f"[{step.delivery_mode}]" if step.delivery_mode else ""
                lines.append(
                    f"    * {step.from_lifeline} -> {step.to_lifeline} : "
                    f"{step.action_name} {mode} ({step.message_kind})"
                )
    return "\n".join(lines)


def _render_api_schema() -> str:
    schema_dump = json.dumps(ApiDesign.model_json_schema(), indent=2)
    return f"Target JSON Schema for ApiDesign:\n{schema_dump}"


def build_api_initial_messages(task: ApiDesignTask) -> list[Message]:
    user_content: str = "\n\n".join(
        [
            "Design the complete REST API specification for the given system.",
            render_scenario_summary(task.scenario),
            render_c4_components(task.architecture_graph, heading=_C4_HEADING),
            _render_sequence_context(task.sequence_scenarios),
            _render_api_schema(),
            "Generate the complete ApiDesign JSON matching all specifications.",
        ]
    )
    return [
        Message(role=MessageRole.SYSTEM, content=API_DESIGN_SYSTEM_PROMPT),
        Message(role=MessageRole.USER, content=user_content),
    ]


def build_api_repair_messages(task: ApiDesignTask) -> list[Message]:
    user_content: str = "\n\n".join(
        [
            "Your previous API Design JSON output was invalid.",
            (
                "Fix ALL detected problems listed below and return the complete "
                "corrected JSON object."
            ),
            f"Previous response:\n{task.previous_payload or ''}",
            render_feedback(
                task.validation_feedback,
                task.parsing_failures,
                empty_message=_EMPTY_FEEDBACK_MESSAGE,
            ),
            render_c4_components(task.architecture_graph, heading=_C4_HEADING),
            _render_api_schema(),
        ]
    )
    return [
        Message(role=MessageRole.SYSTEM, content=API_DESIGN_SYSTEM_PROMPT),
        Message(role=MessageRole.USER, content=user_content),
    ]
