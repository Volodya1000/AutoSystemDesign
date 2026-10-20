"""Mean latency on the critical path via the Allen-Cunneen approximation.

This module estimates per-node mean queue wait and response time. It does not
validate percentile SLOs: a mean estimate cannot establish a p95 or p99 value.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain.exceptions.model_validation_errors import (
    ModelValidationCode,
    ModelValidationError,
)
from domain.models.nodes import CapacityNode, ClientNode
from domain.performance_analysis.queueing import MAX_SUPPORTED_SERVER_COUNT
from domain.specifications.traffic_flow import compute_node_incoming_rps

if TYPE_CHECKING:
    from domain.models.edges import Edge
    from domain.models.scenarios import DesignScenario, WorkloadProfile
    from domain.models.topology import ArchitectureGraph


@dataclass(frozen=True)
class CriticalPathResult:
    """Mean-latency estimates and the critical path when it can be evaluated."""

    total_latency_ms: float | None
    path_node_ids: tuple[str, ...]
    node_latencies_ms: dict[str, float | None]
    node_queue_wait_ms: dict[str, float | None]
    edge_latencies_ms: tuple[float, ...]


def _longest_path_dp(
    node_ids: list[str],
    order: list[str],
    sync_edges: list[Edge],
    node_latencies: dict[str, float],
) -> tuple[dict[str, float], dict[str, str | None], dict[str, float]]:
    """Kahn-order DP over synchronous edges."""
    outgoing: dict[str, list[Edge]] = {}
    for edge in sync_edges:
        outgoing.setdefault(edge.source_identifier, []).append(edge)

    dist: dict[str, float] = {
        identifier: node_latencies.get(identifier, 0.0) for identifier in node_ids
    }
    predecessor: dict[str, str | None] = {identifier: None for identifier in node_ids}
    pred_edge_latency: dict[str, float] = {identifier: 0.0 for identifier in node_ids}

    for node_id in order:
        for edge in outgoing.get(node_id, []):
            target = edge.target_identifier
            if target not in dist:
                continue
            candidate = (
                dist[node_id]
                + edge.network_latency_milliseconds
                + node_latencies.get(target, 0.0)
            )
            if candidate > dist[target]:
                dist[target] = candidate
                predecessor[target] = node_id
                pred_edge_latency[target] = edge.network_latency_milliseconds

    return dist, predecessor, pred_edge_latency


def _reconstruct_path(
    end_node: str,
    predecessor: dict[str, str | None],
    pred_edge_latency: dict[str, float],
) -> tuple[list[str], list[float]]:
    """Reconstruct the selected path and its edge latencies."""
    path: list[str] = []
    edge_latencies: list[float] = []
    current: str | None = end_node

    while current is not None:
        path.append(current)
        pred = predecessor[current]
        if pred is not None:
            edge_latencies.append(pred_edge_latency[current])
        current = pred

    path.reverse()
    edge_latencies.reverse()
    return path, edge_latencies


def _topological_order(node_ids: list[str], edges: list[Edge]) -> list[str]:
    """Kahn topological order over the supplied edge subset."""
    in_degree: dict[str, int] = {identifier: 0 for identifier in node_ids}
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


def _reachable_sync_node_ids(
    node_ids: list[str],
    client_ids: list[str],
    sync_edges: list[Edge],
) -> list[str]:
    """Return nodes reachable from a client through synchronous edges only."""
    valid_node_ids = set(node_ids)
    outgoing: dict[str, list[str]] = {}
    for edge in sync_edges:
        if (
            edge.source_identifier in valid_node_ids
            and edge.target_identifier in valid_node_ids
        ):
            outgoing.setdefault(edge.source_identifier, []).append(
                edge.target_identifier
            )

    reachable = set(client_ids)
    pending: deque[str] = deque(client_ids)
    while pending:
        source = pending.popleft()
        for target in outgoing.get(source, []):
            if target not in reachable:
                reachable.add(target)
                pending.append(target)

    return [identifier for identifier in node_ids if identifier in reachable]


def _calculate_ggc_wait_ms(
    mean: float,
    std: float,
    incoming_rps: float,
    server_count: int,
) -> float | None:
    total_service_rate = server_count * 1000.0 / mean
    if not math.isfinite(total_service_rate) or total_service_rate <= 0.0:
        return None
    utilization_ratio = incoming_rps / total_service_rate
    if not math.isfinite(utilization_ratio) or utilization_ratio >= 1.0:
        return None
    service_variance_ratio = (std / mean) ** 2
    if not math.isfinite(service_variance_ratio):
        return None
    exponent = math.sqrt(2.0 * (server_count + 1.0)) - 1.0
    mean_wait = (
        (1.0 + service_variance_ratio)
        / 2.0
        * utilization_ratio**exponent
        / (server_count * (1.0 - utilization_ratio))
        * mean
    )
    return mean_wait if math.isfinite(mean_wait) and mean_wait >= 0.0 else None


def _node_queue_wait_ms(node: CapacityNode, incoming_rps: float) -> float | None:
    """Estimate mean queue wait with Allen-Cunneen, or return None if unsupported."""
    mean = node.mean_processing_time_milliseconds
    std = node.standard_deviation_processing_time
    if not all(math.isfinite(value) for value in (incoming_rps, mean, std)):
        return None
    if incoming_rps < 0.0 or mean <= 0.0 or std < 0.0:
        return None
    if incoming_rps == 0.0:
        return 0.0
    server_count = node.queueing_server_count
    if server_count is None or server_count > MAX_SUPPORTED_SERVER_COUNT:
        return None
    return _calculate_ggc_wait_ms(mean, std, incoming_rps, server_count)


def _compute_node_latencies(
    graph: ArchitectureGraph,
    workload: WorkloadProfile,
) -> tuple[dict[str, float | None], dict[str, float | None]]:
    incoming = compute_node_incoming_rps(graph, workload)
    latencies: dict[str, float | None] = {}
    queue_waits: dict[str, float | None] = {}

    for node in graph.nodes:
        if isinstance(node, ClientNode):
            latencies[node.identifier] = 0.0
            queue_waits[node.identifier] = None
        elif isinstance(node, CapacityNode):
            queue_wait = _node_queue_wait_ms(node, incoming.get(node.identifier, 0.0))
            queue_waits[node.identifier] = queue_wait
            if queue_wait is None:
                latencies[node.identifier] = None
                continue
            response_time = queue_wait + node.mean_processing_time_milliseconds
            latencies[node.identifier] = (
                response_time if math.isfinite(response_time) else None
            )
        else:
            latencies[node.identifier] = 0.0
            queue_waits[node.identifier] = None

    return latencies, queue_waits


def _compute_synchronous_critical_path(
    graph: ArchitectureGraph,
    node_latencies: dict[str, float | None],
) -> tuple[float | None, tuple[str, ...], tuple[float, ...]]:
    node_ids = [node.identifier for node in graph.nodes]
    if not node_ids:
        return 0.0, (), ()

    sync_edges = [edge for edge in graph.edges if not edge.protocol.is_asynchronous]
    client_ids = [
        node.identifier for node in graph.nodes if isinstance(node, ClientNode)
    ]
    reachable_node_ids = _reachable_sync_node_ids(node_ids, client_ids, sync_edges)
    if not reachable_node_ids:
        return None, (), ()

    relevant_latencies = {
        identifier: node_latencies[identifier] for identifier in reachable_node_ids
    }
    if any(latency is None for latency in relevant_latencies.values()):
        return None, (), ()

    known_node_latencies = {
        identifier: latency
        for identifier, latency in relevant_latencies.items()
        if latency is not None
    }
    reachable_edges = [
        edge
        for edge in sync_edges
        if edge.source_identifier in reachable_node_ids
        and edge.target_identifier in reachable_node_ids
    ]
    order = _topological_order(reachable_node_ids, reachable_edges)
    dist, predecessor, pred_edge_latency = _longest_path_dp(
        reachable_node_ids,
        order,
        reachable_edges,
        known_node_latencies,
    )
    end_node = max(dist, key=dist.__getitem__)
    if not math.isfinite(dist[end_node]):
        return None, (), ()

    path, edge_latencies = _reconstruct_path(end_node, predecessor, pred_edge_latency)
    return dist[end_node], tuple(path), tuple(edge_latencies)


def compute_critical_path(
    graph: ArchitectureGraph,
    scenario: DesignScenario,
) -> CriticalPathResult | None:
    """Estimate the synchronous mean-latency path, or return None without workload."""
    if scenario.workload is None:
        return None

    node_latencies, queue_waits = _compute_node_latencies(graph, scenario.workload)
    total_latency, path_node_ids, edge_latencies = _compute_synchronous_critical_path(
        graph, node_latencies
    )
    return CriticalPathResult(
        total_latency_ms=total_latency,
        path_node_ids=path_node_ids,
        node_latencies_ms=node_latencies,
        node_queue_wait_ms=queue_waits,
        edge_latencies_ms=edge_latencies,
    )
