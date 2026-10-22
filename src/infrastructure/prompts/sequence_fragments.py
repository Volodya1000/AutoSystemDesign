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
        "4. Every declared lifeline MUST participate in at least one "
        "message step. Do not declare unused lifelines: an unused "
        "participant renders as an empty, disconnected actor.\n"
        "5. Set 'delivery_mode' explicitly on every MessageStep: use "
        "'sync' for request / response / user_action and 'async' for "
        "event / notification. Messages with message_kind 'event' or "
        "'notification' MUST have delivery_mode='async'.\n"
        "6. A boundary client component (a ComponentLifeline whose "
        "architecture_node_id references a 'client' node) must belong to "
        "exactly one business role. Two different actors must not "
        "interact through the same client component; give each actor its "
        "own client component instead.\n"
        "7. Build the scenario in this order: first define the complete "
        "message steps and their from_lifeline/to_lifeline participants; "
        "then build the 'lifelines' array from those participants only. "
        "Do not add a lifeline just because a component exists in the C4 "
        "design or role catalog.\n"
        "8. Before returning JSON, collect the set of every lifeline_id "
        "referenced by every message step, including nested 'alt' branches. "
        "Make sure each declared lifeline appears in that set and every "
        "referenced lifeline is declared. Remove any unused lifeline.\n"
        "9. Keep the two component identifiers distinct in meaning: "
        "'architecture_node_id' links a ComponentLifeline to a C4 node, "
        "while 'lifeline_id' is the identifier used by message endpoints. "
        "If a message involves a C4 node, include a ComponentLifeline for it "
        "and use that lifeline's lifeline_id, not the C4 node identifier, "
        "as the message endpoint unless both identifiers are identical.\n"
        "Do not include comments or Markdown wrappers."
    )
