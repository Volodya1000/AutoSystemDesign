import json
from typing import Final

from domain.models.roles import ProjectRolesCatalog
from domain.models.sequence import InteractionScenario
from domain.models.topology import ArchitectureGraph

SEQUENCE_SYSTEM_PROMPT: Final[str] = (
    "You are a senior software architect designing UML Sequence diagrams. "
    "You always answer with EXACTLY ONE valid JSON object. Your response MUST begin "
    "with the '{' character and MUST end with the '}' character: no markdown, no code "
    "fences, no comments, no explanations, no thinking out loud. "
    "Strictly adhere to the provided JSON schema."
)


def render_c4_context(graph: ArchitectureGraph) -> str:
    lines = ["Available architectural components (nodes) from the generated C4 design:"]
    for node in graph.nodes:
        lines.append(f"- {node.identifier} (type: {node.node_type.value})")
    lines.append(
        "\nWhen creating a ComponentLifeline, you MUST use one of these exact "
        "identifiers in the 'architecture_node_id' field."
    )
    return "\n".join(lines)


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
