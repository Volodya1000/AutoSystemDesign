"""Normalize generated sequence participants against the C4 graph."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, cast

from domain.models.enums import NodeType

if TYPE_CHECKING:
    from collections.abc import Iterator

    from domain.models.topology import ArchitectureGraph

_ENDPOINT_FIELDS: tuple[str, str] = ("from_lifeline", "to_lifeline")


def normalize_interaction_payload(payload: object, graph: ArchitectureGraph) -> object:
    """Resolve unambiguous C4 node references before strict scenario validation.

    A message may name a C4 node directly even when its ComponentLifeline uses
    a different lifeline_id, or omit the lifeline for a referenced backend node.
    Only unambiguous backend references are repaired. Unknown IDs, ambiguous
    mappings, and missing client lifelines remain invalid.
    """
    normalized_payload = _as_dict(deepcopy(payload))
    if normalized_payload is None:
        return payload

    lifelines = _as_list(normalized_payload.get("lifelines"))
    steps = _as_list(normalized_payload.get("steps"))
    if lifelines is None or steps is None:
        return normalized_payload

    declared_ids, component_lifelines = _index_lifelines(lifelines)
    messages = list(_iter_message_steps(steps))
    unresolved_ids: set[str] = set()
    for message in messages:
        for field in _ENDPOINT_FIELDS:
            reference = message.get(field)
            if isinstance(reference, str) and reference not in declared_ids:
                unresolved_ids.add(reference)

    aliases = _resolve_lifeline_references(
        unresolved_ids,
        lifelines,
        component_lifelines,
        graph,
    )
    for message in messages:
        for field in _ENDPOINT_FIELDS:
            reference = message.get(field)
            if isinstance(reference, str) and reference in aliases:
                message[field] = aliases[reference]

    return normalized_payload


def _index_lifelines(
    lifelines: list[object],
) -> tuple[set[str], dict[str, list[str]]]:
    """Index declared participant IDs and component lifelines by C4 node ID."""
    declared_ids: set[str] = set()
    component_lifelines: dict[str, list[str]] = {}
    for raw_lifeline in lifelines:
        lifeline = _as_dict(raw_lifeline)
        if lifeline is None:
            continue

        lifeline_id = lifeline.get("lifeline_id")
        if isinstance(lifeline_id, str):
            declared_ids.add(lifeline_id)
        if lifeline.get("kind") != "component":
            continue

        node_id = lifeline.get("architecture_node_id")
        if isinstance(node_id, str) and isinstance(lifeline_id, str):
            component_lifelines.setdefault(node_id, []).append(lifeline_id)

    return declared_ids, component_lifelines


def _resolve_lifeline_references(
    unresolved_ids: set[str],
    lifelines: list[object],
    component_lifelines: dict[str, list[str]],
    graph: ArchitectureGraph,
) -> dict[str, str]:
    """Map unique C4 references or add omitted non-client participants."""
    aliases: dict[str, str] = {}
    nodes_by_id = {node.identifier: node for node in graph.nodes}

    for reference in sorted(unresolved_ids):
        candidates = component_lifelines.get(reference, [])
        if len(candidates) == 1:
            aliases[reference] = candidates[0]
            continue
        if candidates:
            continue

        node = nodes_by_id.get(reference)
        if node is None or node.node_type is NodeType.CLIENT:
            continue

        lifelines.append(
            {
                "kind": "component",
                "lifeline_id": reference,
                "architecture_node_id": reference,
                "display_name": node.identifier,
                "description": "Architectural component referenced by a message.",
            }
        )

    return aliases


def _iter_message_steps(steps: list[object]) -> Iterator[dict[str, object]]:
    """Yield message steps from the complete nested interaction tree."""
    for raw_step in steps:
        step = _as_dict(raw_step)
        if step is None:
            continue

        if step.get("kind") == "message":
            yield step
        else:
            yield from _iter_nested_message_steps(step)


def _iter_nested_message_steps(step: dict[str, object]) -> Iterator[dict[str, object]]:
    """Yield messages contained by a nested AST step."""
    if step.get("kind") == "alt":
        yield from _iter_branch_message_steps(step)
    elif step.get("kind") in {"opt", "loop"}:
        nested_steps = _as_list(step.get("steps"))
        if nested_steps is not None:
            yield from _iter_message_steps(nested_steps)


def _iter_branch_message_steps(step: dict[str, object]) -> Iterator[dict[str, object]]:
    """Yield messages from each branch of an alternative step."""
    branches = _as_list(step.get("branches"))
    if branches is None:
        return

    for raw_branch in branches:
        branch = _as_dict(raw_branch)
        if branch is None:
            continue
        nested_steps = _as_list(branch.get("steps"))
        if nested_steps is not None:
            yield from _iter_message_steps(nested_steps)


def _as_dict(value: object) -> dict[str, object] | None:
    """Return a dictionary when the value has the expected JSON shape."""
    if not isinstance(value, dict):
        return None
    return cast("dict[str, object]", value)


def _as_list(value: object) -> list[object] | None:
    """Return a list when the value has the expected JSON shape."""
    if not isinstance(value, list):
        return None
    return cast("list[object]", value)
