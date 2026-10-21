# Copyright (c) 2026 Volodya1000
"""Prompt builders for the sequence-diagram generation stage."""

import json

from application.tasks import SequenceInteractionTask, SequenceRoleTask
from domain.models.topology import ArchitectureGraph
from infrastructure.llm.models import Message, MessageRole
from infrastructure.prompts._c4_context import render_c4_components
from infrastructure.prompts._feedback import render_feedback
from infrastructure.prompts.fragments_scenario import render_scenario_summary
from infrastructure.prompts.sequence_fragments import (
    SEQUENCE_SYSTEM_PROMPT,
    render_interaction_schema,
    render_roles_schema,
)

_EMPTY_FEEDBACK_MESSAGE: str = "No problems reported; re-check the schema."

_C4_HEADING: str = (
    "Available architectural components (nodes) from the generated C4 design:"
)

_C4_FOOTER: str = (
    "When creating a ComponentLifeline, you MUST use one of these exact "
    "identifiers in the 'architecture_node_id' field."
)


def _render_c4_context(graph: ArchitectureGraph) -> str:
    return render_c4_components(graph, heading=_C4_HEADING, footer=_C4_FOOTER)


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
            render_feedback(
                task.validation_feedback,
                task.parsing_failures,
                empty_message=_EMPTY_FEEDBACK_MESSAGE,
            ),
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
            _render_c4_context(task.architecture_graph),
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
            render_feedback(
                task.validation_feedback,
                task.parsing_failures,
                empty_message=_EMPTY_FEEDBACK_MESSAGE,
            ),
            _render_c4_context(task.architecture_graph),
            render_interaction_schema(),
            f"Set requirement_identifier to '{task.requirement.identifier}'.",
        ]
    )
    return [
        Message(role=MessageRole.SYSTEM, content=SEQUENCE_SYSTEM_PROMPT),
        Message(role=MessageRole.USER, content=user_content),
    ]
