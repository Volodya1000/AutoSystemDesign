"""Theoretical latency on the critical path via Allen-Cunneen approximation.

Pure module. Computes per-node mean sojourn time (queue + service) and
the worst synchronous path through the graph, then compares to each
LatencyRequirement. Mean latency is a necessary condition: if the mean
exceeds the SLA, the 99th percentile cannot pass either.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain.exceptions.architecture_errors import (
    ArchitectureValidationError,
    TheoreticalLatencyViolationError,
)
from domain.exceptions.model_validation_errors import (
    ModelValidationCode,
    ModelValidationError,
)
from domain.models.nodes import CapacityNode, ClientNode
from domain.models.requirements import LatencyRequirement
from domain.specifications.interfaces import ScenarioValidator, ValidationResult
from domain.specifications.traffic_flow import compute_node_incoming_rps

if TYPE_CHECKING:
    from domain.models.edges import Edge
    from domain.models.scenarios import DesignScenario, WorkloadProfile
    from domain.models.topology import ArchitectureGraph


@dataclass(frozen=True)
class CriticalPathResult:
    """Worst-case synchronous path with latency contributions."""

    total_latency_ms: float
    path_node_ids: tuple[str, ...]
    node_latencies_ms: dict[str, float]
    edge_latencies_ms: tuple[float, ...]


def _longest_path_dp(
    node_ids: list[str],
    order: list[str],
    sync_edges: list[Edge],
    node_latencies: dict[str, float],
) -> tuple[dict[str, float], dict[str, str | None], dict[str, float]]:
    """Kahn-order DP over sync edges.

    Returns ``(dist, predecessor, pred_edge_latency)``: the longest path to
    each node, its predecessor, and the edge latency leading into it.
    ``dist`` is seeded with each node's own processing time so an isolated
    node still has a defined value.
    """
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
    """Walks predecessor links back to the source and reverses the result.

    ``edge_latencies[i]`` is the latency of the edge connecting
    ``path[i]`` to ``path[i + 1]``; the list is one shorter than ``path``.
    """
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


def _node_sojourn_ms(node: CapacityNode, incoming_rps: float) -> float:
    """Mean sojourn time via Allen-Cunneen.

    At c=1 this reduces exactly to Kingman/P-K; at c>1 it correctly
    amortizes queueing across parallel slots, avoiding false positives for
    nodes with high maximum_concurrency.
    """
    mean = node.mean_processing_time_milliseconds
    std = node.standard_deviation_processing_time
    c = node.replicas_count * node.maximum_concurrency
    mu_total = c * 1000.0 / mean
    rho = incoming_rps / mu_total

    if rho >= 1.0:
        # Saturated node: queue is unbounded, latency is genuinely infinite.
        return float("inf")

    c_s = std / mean
    c_a_squared = 1.0  # Poisson arrivals
    exponent = math.sqrt(2.0 * (c + 1.0)) - 1.0
    e_wq = (c_a_squared + c_s * c_s) / 2.0 * (rho**exponent) / (c * (1.0 - rho)) * mean
    return e_wq + mean


def _compute_node_latencies(
    graph: ArchitectureGraph,
    workload: WorkloadProfile,
) -> dict[str, float]:
    incoming = compute_node_incoming_rps(graph, workload)
    latencies: dict[str, float] = {}

    for node in graph.nodes:
        if isinstance(node, ClientNode):
            latencies[node.identifier] = 0.0
        elif isinstance(node, CapacityNode):
            latencies[node.identifier] = _node_sojourn_ms(
                node, incoming.get(node.identifier, 0.0)
            )
        else:
            latencies[node.identifier] = 0.0

    return latencies


def compute_critical_path(
    graph: ArchitectureGraph,
    scenario: DesignScenario,
) -> CriticalPathResult | None:
    """Returns the worst synchronous path, or None when workload is absent.

    Only synchronous edges are traversed: async fire-and-forget calls do not
    block the caller and therefore do not contribute to user-visible latency.
    """
    if scenario.workload is None:
        return None

    node_latencies = _compute_node_latencies(graph, scenario.workload)
    node_ids = [node.identifier for node in graph.nodes]

    if not node_ids:
        return CriticalPathResult(
            total_latency_ms=0.0,
            path_node_ids=(),
            node_latencies_ms=node_latencies,
            edge_latencies_ms=(),
        )

    sync_edges = [edge for edge in graph.edges if not edge.protocol.is_asynchronous]
    order = _topological_order(node_ids, sync_edges)
    dist, predecessor, pred_edge_latency = _longest_path_dp(
        node_ids, order, sync_edges, node_latencies
    )
    end_node = max(dist, key=dist.__getitem__)
    path, edge_latencies = _reconstruct_path(end_node, predecessor, pred_edge_latency)

    return CriticalPathResult(
        total_latency_ms=dist[end_node],
        path_node_ids=tuple(path),
        node_latencies_ms=node_latencies,
        edge_latencies_ms=tuple(edge_latencies),
    )


class LatencySloValidator(ScenarioValidator):
    """Checks the critical path against every LatencyRequirement."""

    def validate(
        self,
        graph: ArchitectureGraph,
        scenario: DesignScenario,
    ) -> ValidationResult:
        if scenario.workload is None:
            return ValidationResult(errors=[])

        try:
            critical = compute_critical_path(graph, scenario)
        except ValueError:
            # Cycle detection is owned by StructuralTopologyValidator; see
            # the matching guard in CapacitySaturationValidator.
            return ValidationResult(errors=[])

        if critical is None:
            return ValidationResult(errors=[])

        errors: list[ArchitectureValidationError] = []

        for requirement in scenario.requirements:
            if not isinstance(requirement, LatencyRequirement):
                continue
            if not requirement.is_met_requirement(critical.total_latency_ms):
                errors.append(
                    TheoreticalLatencyViolationError(
                        critical_path_node_identifiers=list(critical.path_node_ids),
                        calculated_mean_latency_milliseconds=critical.total_latency_ms,
                        target_threshold_milliseconds=requirement.threshold_value,
                    )
                )

        return ValidationResult(errors=errors)
