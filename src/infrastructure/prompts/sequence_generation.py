import json

from application.tasks import SequenceContextTask, SequenceInteractionTask
from infrastructure.llm.models import Message, MessageRole
from infrastructure.prompts.fragments import (
    STRUCTURED_OUTPUT_SYSTEM_PROMPT,
    render_scenario_summary,
)
from infrastructure.prompts.sequence_fragments import (
    render_c4_context,
    render_context_schema,
    render_interaction_schema,
)


def build_context_initial_messages(task: SequenceContextTask) -> list[Message]:
    user_content = "\n\n".join(
        [
            "Analyze the following business scenario.",
            "Your task is to extract/formulate the functional requirements and build the global catalog of business roles.",
            render_scenario_summary(task.scenario),
            render_context_schema(),
        ]
    )
    return [
        Message(role=MessageRole.SYSTEM, content=STRUCTURED_OUTPUT_SYSTEM_PROMPT),
        Message(role=MessageRole.USER, content=user_content),
    ]


def build_context_repair_messages(task: SequenceContextTask) -> list[Message]:
    user_content = "\n\n".join(
        [
            "Your previous JSON answer for the context parsing was invalid.",
            "Fix ALL the parsing problems listed below and return the complete corrected JSON object.",
            f"Previous answer:\n{task.previous_payload or ''}",
            _render_parsing_problems(task.parsing_failures),
            render_context_schema(),
        ]
    )
    return [
        Message(role=MessageRole.SYSTEM, content=STRUCTURED_OUTPUT_SYSTEM_PROMPT),
        Message(role=MessageRole.USER, content=user_content),
    ]


def build_interaction_initial_messages(task: SequenceInteractionTask) -> list[Message]:
    user_content = "\n\n".join(
        [
            "You are tasked with generating ONE UML Sequence Diagram (InteractionScenario) for a specific functional requirement.",
            "Target Functional Requirement:",
            f"- ID: {task.requirement.identifier}",
            f"- Name: {task.requirement.name}",
            f"- Description: {task.requirement.text}",
            "\nGlobal Roles Catalog:",
            json.dumps(task.roles_catalog.model_dump(), indent=2),
            render_c4_context(task.architecture_graph),
            render_interaction_schema(),
            "Ensure all UserLifelines reference a valid business_role_id from the catalog, and ComponentLifelines reference an architecture_node_id.",
        ]
    )
    return [
        Message(role=MessageRole.SYSTEM, content=STRUCTURED_OUTPUT_SYSTEM_PROMPT),
        Message(role=MessageRole.USER, content=user_content),
    ]


def build_interaction_repair_messages(task: SequenceInteractionTask) -> list[Message]:
    user_content = "\n\n".join(
        [
            "Your previous JSON answer for the interaction scenario was invalid.",
            "Fix ALL the problems listed below and return the complete corrected JSON object.",
            f"Target Requirement ID: {task.requirement.identifier}",
            f"Previous answer:\n{task.previous_payload or ''}",
            _render_validation_problems(task),
            render_c4_context(task.architecture_graph),
            render_interaction_schema(),
        ]
    )
    return [
        Message(role=MessageRole.SYSTEM, content=STRUCTURED_OUTPUT_SYSTEM_PROMPT),
        Message(role=MessageRole.USER, content=user_content),
    ]


def _render_parsing_problems(parsing_failures) -> str:
    entries = [
        f"[{f.error_type}] {f.message} (at {f.location})" for f in parsing_failures
    ]
    if not entries:
        return "No specific parsing problems were reported."
    lines = ["Detected parsing problems:"]
    lines.extend(f"{index}. {entry}" for index, entry in enumerate(entries, start=1))
    return "\n".join(lines)


def _render_validation_problems(task: SequenceInteractionTask) -> str:
    entries = [f"[{fb.error_code}] {fb.message}" for fb in task.validation_feedback]
    entries.extend(
        f"[{f.error_type}] {f.message} (at {f.location})" for f in task.parsing_failures
    )
    if not entries:
        return "No specific validation problems were reported."
    lines = ["Detected logic and AST problems:"]
    lines.extend(f"{index}. {entry}" for index, entry in enumerate(entries, start=1))
    return "\n".join(lines)
