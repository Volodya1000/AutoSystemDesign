import json

from application.tasks import SequenceInteractionTask, SequenceRoleTask
from infrastructure.llm.models import Message, MessageRole
from infrastructure.prompts.fragments import render_scenario_summary
from infrastructure.prompts.sequence_fragments import (
    SEQUENCE_SYSTEM_PROMPT,
    render_c4_context,
    render_interaction_schema,
    render_roles_schema,
)


def build_roles_initial_messages(task: SequenceRoleTask) -> list[Message]:
    user_content = "\n\n".join(
        [
            "Analyze the following business scenario.",
            (
                "Your task is to extract and define the global catalog of "
                "business roles (ProjectRolesCatalog)."
            ),
            render_scenario_summary(task.scenario),
            render_roles_schema(),
        ]
    )
    return [
        Message(role=MessageRole.SYSTEM, content=SEQUENCE_SYSTEM_PROMPT),
        Message(role=MessageRole.USER, content=user_content),
    ]


def build_roles_repair_messages(task: SequenceRoleTask) -> list[Message]:
    user_content = "\n\n".join(
        [
            "Your previous JSON answer for the business roles catalog was invalid.",
            (
                "Fix ALL the problems listed below and return the complete "
                "corrected JSON object."
            ),
            f"Previous answer:\n{task.previous_payload or ''}",
            _render_feedback(task.validation_feedback, task.parsing_failures),
            render_roles_schema(),
        ]
    )
    return [
        Message(role=MessageRole.SYSTEM, content=SEQUENCE_SYSTEM_PROMPT),
        Message(role=MessageRole.USER, content=user_content),
    ]


def build_interaction_initial_messages(task: SequenceInteractionTask) -> list[Message]:
    user_content = "\n\n".join(
        [
            (
                "Generate a detailed UML Sequence Diagram (InteractionScenario) "
                "for the specified functional requirement."
            ),
            "Target Functional Requirement:",
            f"- ID: {task.requirement.identifier}",
            f"- Name: {task.requirement.name}",
            f"- Description: {task.requirement.text}",
            "Global Roles Catalog:",
            json.dumps(task.roles_catalog.model_dump(), indent=2),
            render_c4_context(task.architecture_graph),
            render_interaction_schema(),
            f"Set requirement_identifier to '{task.requirement.identifier}'.",
        ]
    )
    return [
        Message(role=MessageRole.SYSTEM, content=SEQUENCE_SYSTEM_PROMPT),
        Message(role=MessageRole.USER, content=user_content),
    ]


def build_interaction_repair_messages(task: SequenceInteractionTask) -> list[Message]:
    user_content = "\n\n".join(
        [
            "Your previous JSON answer for the interaction scenario was invalid.",
            (
                "Fix ALL the problems listed below and return the complete "
                "corrected JSON object."
            ),
            f"Target Requirement ID: {task.requirement.identifier}",
            f"Previous answer:\n{task.previous_payload or ''}",
            _render_feedback(task.validation_feedback, task.parsing_failures),
            render_c4_context(task.architecture_graph),
            render_interaction_schema(),
            f"Set requirement_identifier to '{task.requirement.identifier}'.",
        ]
    )
    return [
        Message(role=MessageRole.SYSTEM, content=SEQUENCE_SYSTEM_PROMPT),
        Message(role=MessageRole.USER, content=user_content),
    ]


def _render_feedback(validation_feedback, parsing_failures) -> str:
    entries = [f"[{fb.error_code}] {fb.message}" for fb in validation_feedback]
    entries.extend(
        f"[{f.error_type}] {f.message} (at {f.location})" for f in parsing_failures
    )
    if not entries:
        return (
            "No specific problems reported; re-check the schema rules "
            "and correct the JSON."
        )
    lines = ["Detected problems:"]
    lines.extend(f"{idx}. {entry}" for idx, entry in enumerate(entries, start=1))
    return "\n".join(lines)
