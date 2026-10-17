"""Fragments for sequence-diagram prompts: system prompt and schemas."""

import json
from typing import Final

from domain.models.roles import ProjectRolesCatalog
from domain.models.sequence import InteractionScenario

SEQUENCE_SYSTEM_PROMPT: Final[str] = (
    "You are a senior software architect designing UML Sequence diagrams. "
    "You always answer with EXACTLY ONE valid JSON object. Your response MUST begin "
    "with the '{' character and MUST end with the '}' character: no markdown, no code "
    "fences, no comments, no explanations, no thinking out loud. "
    "Strictly adhere to the provided JSON schema."
)


def render_roles_schema() -> str:
    schema = ProjectRolesCatalog.model_json_schema()
    schema_dump = json.dumps(schema, indent=2)
    return (
        "Output format: A single JSON object matching the following JSON "
        "Schema for ProjectRolesCatalog.\n"
        f"{schema_dump}\n\n"
        "Do not include comments or Markdown wrappers."
    )


def render_interaction_schema() -> str:
    schema = InteractionScenario.model_json_schema()
    schema_dump = json.dumps(schema, indent=2)
    return (
        "Output format: A single JSON object matching the following JSON "
        "Schema for InteractionScenario.\n"
        f"{schema_dump}\n\n"
        "IMPORTANT RULES FOR AST STEPS:\n"
        "1. Every branch in an 'alt' block must have at least one step.\n"
        "2. The 'else' branch (where condition is null) must be the last "
        "branch in the list if it exists.\n"
        "3. All from_lifeline and to_lifeline fields must refer to a "
        "defined lifeline_id from your 'lifelines' array.\n"
        "Do not include comments or Markdown wrappers."
    )
