"""Rendering of C4 architecture components for LLM prompts.

Two prompts (API design, sequence interaction) list the available C4 nodes
to constrain what the model may reference. The body format is identical:
one ``- <id> (type: <node_type>)`` line per node. Only the surrounding
prose differs, so the caller passes a heading and an optional footer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.models.topology import ArchitectureGraph


def render_c4_components(
    graph: ArchitectureGraph,
    *,
    heading: str,
    footer: str | None = None,
) -> str:
    """Render components, directed links and an optional footer.

    When ``footer`` is provided, it is separated from the node list by a
    blank line so callers pass plain prose without a leading newline.
    """
    lines: list[str] = [heading]
    lines.extend(
        f"- {node.identifier} (type: {node.node_type.value})" for node in graph.nodes
    )
    lines.append("Directed C4 links (requests must follow these exact links):")
    lines.extend(
        f"- {edge.source_identifier} -> {edge.target_identifier}: "
        f"{edge.protocol.name}, "
        f"{'async' if edge.protocol.is_asynchronous else 'sync'}, "
        f"routing={edge.routing_mode.value}"
        for edge in graph.edges
    )
    lines.append(
        "Do not invent links between existing nodes. A synchronous response "
        "may return along its preceding request; do not add reverse C4 links. "
        "A business function requiring unavailable dependencies cannot be "
        "implemented by inventing a call."
    )
    if footer is not None:
        lines.append("")
        lines.append(footer)
    return "\n".join(lines)
