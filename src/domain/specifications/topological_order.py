"""Topological sorting shared by domain graph calculations."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from domain.exceptions.model_validation_errors import (
    ModelValidationCode,
    ModelValidationError,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain.models.edges import Edge


def topological_order(node_ids: list[str], edges: Sequence[Edge]) -> list[str]:
    """Return Kahn's topological order for the given nodes and edges.

    Edges outside the supplied node set are ignored. Raise a domain validation
    error when the supplied subgraph contains a cycle.
    """
    in_degree: dict[str, int] = dict.fromkeys(node_ids, 0)
    adjacency: dict[str, list[str]] = {identifier: [] for identifier in node_ids}

    for edge in edges:
        if edge.source_identifier in adjacency and edge.target_identifier in in_degree:
            adjacency[edge.source_identifier].append(edge.target_identifier)
            in_degree[edge.target_identifier] += 1

    queue: deque[str] = deque(
        identifier for identifier in node_ids if in_degree[identifier] == 0
    )
    order: list[str] = []

    while queue:
        current = queue.popleft()
        order.append(current)
        for target in adjacency[current]:
            in_degree[target] -= 1
            if in_degree[target] == 0:
                queue.append(target)

    if len(order) != len(node_ids):
        raise ModelValidationError(ModelValidationCode.TOPOLOGY_CYCLE)
    return order
