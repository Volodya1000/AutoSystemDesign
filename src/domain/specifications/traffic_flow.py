"""Deterministic computation of per-node incoming request rates.

Pure module: no I/O, no logging, no clock, no randomness. All inputs are
domain models; the output is a plain mapping. Used by capacity and latency
validators, and by the metrics aggregator.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from domain.exceptions.model_validation_errors import (
    ModelValidationCode,
    ModelValidationError,
)
from domain.models.nodes import CacheNode, ClientNode

if TYPE_CHECKING:
    from domain.models.edges import Edge
    from domain.models.scenarios import WorkloadProfile
    from domain.models.topology import ArchitectureGraph


def _propagate_flows(
    graph: ArchitectureGraph,
    order: list[str],
    flows: dict[str, float],
) -> None:
    """Propagates incoming flows downstream in topological order, in place.

    Each node divides its outgoing rate equally across its outgoing edges;
    a cache propagates only the miss fraction, everything else propagates
    the full rate. Async edges carry load too.
    """
    by_id = {node.identifier: node for node in graph.nodes}
    outgoing: dict[str, list[Edge]] = {}
    for edge in graph.edges:
        outgoing.setdefault(edge.source_identifier, []).append(edge)

    for node_id in order:
        incoming = flows[node_id]
        node = by_id[node_id]

        if isinstance(node, CacheNode):
            outgoing_rps = incoming * (1.0 - node.cache_hit_rate_probability)
        else:
            outgoing_rps = incoming

        edges = outgoing.get(node_id, [])
        if not edges:
            continue

        share = outgoing_rps / len(edges)
        for edge in edges:
            if edge.target_identifier in flows:
                flows[edge.target_identifier] += share


def _topological_order(graph: ArchitectureGraph) -> list[str]:
    """Return node identifiers in Kahn topological order.

    Raises ValueError when the graph contains a cycle. Structural
    validation normally guarantees a DAG; this is a defensive contract check.
    """
    node_ids: list[str] = [node.identifier for node in graph.nodes]
    in_degree: dict[str, int] = {identifier: 0 for identifier in node_ids}
    adjacency: dict[str, list[str]] = {identifier: [] for identifier in node_ids}

    for edge in graph.edges:
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


def compute_node_incoming_rps(
    graph: ArchitectureGraph,
    workload: WorkloadProfile,
) -> dict[str, float]:
    """Return the incoming request rate (RPS) for every node.

    Rules:
    * Peak load is divided equally between client nodes.
    * Each node propagates its incoming rate to outgoing edges equally.
    * Cache nodes propagate only the miss fraction:
      incoming * (1 - cache_hit_rate_probability).
    * All other node types propagate the full incoming rate.
    * Every node in the graph is present in the result.

    The graph is assumed to be a DAG. Raises ValueError if a cycle is
    detected, which indicates a pipeline contract violation.
    """
    flows: dict[str, float] = {node.identifier: 0.0 for node in graph.nodes}

    # Detect cycles even when there are no clients: a cyclic graph is never
    # a valid pipeline input, and tests expect a defensive ValueError.
    order: list[str] = _topological_order(graph)

    clients: list[ClientNode] = [
        node for node in graph.nodes if isinstance(node, ClientNode)
    ]
    if not clients:
        return flows

    per_client: float = workload.peak_requests_per_second / len(clients)
    for client in clients:
        flows[client.identifier] = per_client

    _propagate_flows(graph, order, flows)
    return flows
