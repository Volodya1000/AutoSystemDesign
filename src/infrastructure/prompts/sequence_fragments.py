import json

from domain.models.sequence import InteractionScenario
from domain.models.system_design import SystemContextOutput
from domain.models.topology import ArchitectureGraph


def render_c4_context(graph: ArchitectureGraph) -> str:
    lines = ["Available architectural components (nodes) from the generated C4 design:"]
    for node in graph.nodes:
        lines.append(f"- {node.identifier} (type: {node.node_type.value})")
    lines.append(
        "\nWhen creating a ComponentLifeline, you MUST use one of these exact identifiers in the 'architecture_node_id' field."
    )
    return "\n".join(lines)


def render_context_schema() -> str:
    schema = SystemContextOutput.model_json_schema()
    schema_dump = json.dumps(schema, indent=2)
    return (
        "Output format: A single JSON object matching the following JSON Schema.\n"
        f"{schema_dump}\n\n"
        "Do not include comments or Markdown wrappers."
    )


def render_interaction_schema() -> str:
    schema = InteractionScenario.model_json_schema()
    schema_dump = json.dumps(schema, indent=2)
    return (
        "Output format: A single JSON object matching the following JSON Schema.\n"
        f"{schema_dump}\n\n"
        "IMPORTANT RULES FOR AST STEPS:\n"
        "1. Every branch in an 'alt' block must have at least one step.\n"
        "2. The 'else' branch (where condition is null) must be the last branch in the list if it exists.\n"
        "3. All from_lifeline and to_lifeline fields must refer to a defined lifeline_id from your 'lifelines' array.\n"
        "Do not include comments or Markdown wrappers."
    )
