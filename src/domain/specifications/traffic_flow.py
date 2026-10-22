"""Deterministic computation of per-node incoming request rates.

Pure module: no I/O, no logging, no clock, no randomness. All inputs are
domain models; the output is a plain mapping. Used by capacity and latency
validators, and by the metrics aggregator.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.exceptions.model_validation_errors import (
    ModelValidationCode,
    ModelValidationError,
)
from domain.models.enums import EdgeRoutingMode
from domain.models.nodes import CacheNode, ClientNode, DatabaseNode
from domain.specifications.topological_order import topological_order

if TYPE_CHECKING:
    from domain.models.edges import Edge
    from domain.models.scenarios import WorkloadProfile
    from domain.models.topology import ArchitectureGraph


def _allocate_edge_flows(
    edges: list[Edge],
    source_rps: float,
) -> list[tuple[Edge, float]]:
    """Allocate one source rate according to the modes of its outgoing edges."""
    alternative_edges = [
        edge for edge in edges if edge.routing_mode is EdgeRoutingMode.ALTERNATIVE
    ]
    fan_out_edges = [
        edge for edge in edges if edge.routing_mode is EdgeRoutingMode.FAN_OUT
    ]

    allocations: list[tuple[Edge, float]] = [
        (edge, source_rps) for edge in fan_out_edges
    ]
    if alternative_edges:
        share = source_rps / len(alternative_edges)
        allocations.extend((edge, share) for edge in alternative_edges)
    return allocations


def _apply_allocations(
    edges: list[Edge],
    source_rps: float,
    flows: dict[str, float],
    *,
    tracked_target_identifier: str | None = None,
) -> float:
    """Apply edge allocations and optionally return the rate for one target."""
    tracked_rps = 0.0
    for edge, edge_rps in _allocate_edge_flows(edges, source_rps):
        if edge.target_identifier in flows:
            flows[edge.target_identifier] += edge_rps
        if edge.target_identifier == tracked_target_identifier:
            tracked_rps += edge_rps
    return tracked_rps


def _is_database_fallback_edge(
    edge: Edge,
    database_node_identifiers: set[str],
) -> bool:
    return (
        not edge.protocol.is_asynchronous
        and edge.target_identifier in database_node_identifiers
    )


def _propagate_node_flows(
    node_identifier: str,
    outgoing_edges: list[Edge],
    flows: dict[str, float],
    cache_nodes_by_id: dict[str, CacheNode],
    database_node_identifiers: set[str],
) -> None:
    """Propagate one node's traffic, applying cache miss rate to its DB fallback."""
    source_rps = flows[node_identifier]
    cache_target_ids = {
        edge.target_identifier
        for edge in outgoing_edges
        if not edge.protocol.is_asynchronous
        and edge.target_identifier in cache_nodes_by_id
    }
    if len(cache_target_ids) > 1:
        raise ModelValidationError(
            ModelValidationCode.AMBIGUOUS_CACHE_MISS_PATH,
            node_identifier=node_identifier,
        )

    database_fallback_edges = [
        edge
        for edge in outgoing_edges
        if _is_database_fallback_edge(edge, database_node_identifiers)
    ]
    if not cache_target_ids or not database_fallback_edges:
        _apply_allocations(outgoing_edges, source_rps, flows)
        return

    cache_target_id = next(iter(cache_target_ids))
    ordinary_edges = [
        edge
        for edge in outgoing_edges
        if not _is_database_fallback_edge(edge, database_node_identifiers)
    ]
    cache_rps = _apply_allocations(
        ordinary_edges,
        source_rps,
        flows,
        tracked_target_identifier=cache_target_id,
    )
    hit_rate = cache_nodes_by_id[cache_target_id].cache_hit_rate_probability
    miss_rps = cache_rps * (1.0 - hit_rate)
    _apply_allocations(database_fallback_edges, miss_rps, flows)


def _propagate_flows(
    graph: ArchitectureGraph,
    order: list[str],
    flows: dict[str, float],
) -> None:
    """Propagate request flows in topological order, in place."""
    outgoing: dict[str, list[Edge]] = {}
    for edge in graph.edges:
        outgoing.setdefault(edge.source_identifier, []).append(edge)

    cache_nodes_by_id = {
        node.identifier: node for node in graph.nodes if isinstance(node, CacheNode)
    }
    database_node_identifiers = {
        node.identifier for node in graph.nodes if isinstance(node, DatabaseNode)
    }
    for node_identifier in order:
        _propagate_node_flows(
            node_identifier,
            outgoing.get(node_identifier, []),
            flows,
            cache_nodes_by_id,
            database_node_identifiers,
        )


def compute_node_incoming_rps(
    graph: ArchitectureGraph,
    workload: WorkloadProfile,
) -> dict[str, float]:
    """Return the incoming request rate (RPS) for every node.

    Rules:
    * Peak load is divided equally between client nodes.
    * Alternative outgoing edges split the outgoing rate equally.
    * Fan-out edges each receive the full outgoing rate.
    * For a cache reader, the synchronous database edge from the same compute
      node receives only cache-edge traffic * (1 - cache_hit_rate_probability).
    * Every node in the graph is present in the result.

    The graph is assumed to be a DAG. Raises ValueError if a cycle is
    detected, which indicates a pipeline contract violation.
    """
    flows: dict[str, float] = {node.identifier: 0.0 for node in graph.nodes}

    # Detect cycles even when there are no clients: a cyclic graph is never
    # a valid pipeline input, and tests expect a defensive ValueError.
    order: list[str] = topological_order(
        [node.identifier for node in graph.nodes], graph.edges
    )

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
