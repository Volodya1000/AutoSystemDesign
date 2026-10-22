"""Build a performance report from existing domain calculations."""

from __future__ import annotations

from math import isfinite
from typing import TYPE_CHECKING

from domain.models.nodes import CapacityNode
from domain.models.requirements import LatencyRequirement
from domain.performance_analysis.report import (
    NodePerformanceMetrics,
    PerformanceAnalysisReport,
    PerformanceAnalysisStatus,
    PerformanceFinding,
    PerformanceFindingCode,
    PerformanceFindingSeverity,
)
from domain.specifications.capacity_validator import (
    SATURATION_THRESHOLD,
    compute_node_capacity_rps,
    compute_node_utilization,
)
from domain.specifications.latency_validator import (
    CriticalPathResult,
    compute_critical_path,
)
from domain.specifications.traffic_flow import compute_node_incoming_rps

if TYPE_CHECKING:
    from domain.models.scenarios import DesignScenario
    from domain.models.topology import ArchitectureGraph

def build_performance_analysis_report(
    graph: ArchitectureGraph,
    scenario: DesignScenario,
) -> PerformanceAnalysisReport:
    """Build a JSON-ready report without introducing new performance formulas.

    Capacity is known from the node model even without a workload. Load,
    utilization, and latency are left unavailable when the scenario has no
    workload profile. Unavailable latency estimates are represented as null when
    queueing assumptions are unknown or the modeled system is unstable.
    """
    capacity_by_node: dict[str, float] = {
        node.identifier: compute_node_capacity_rps(node)
        for node in graph.nodes
        if isinstance(node, CapacityNode)
    }

    if scenario.workload is None:
        return PerformanceAnalysisReport(
            scenario_identifier=scenario.identifier,
            status=PerformanceAnalysisStatus.UNAVAILABLE,
            nodes=[
                NodePerformanceMetrics(
                    node_identifier=node.identifier,
                    estimated_capacity_requests_per_second=capacity_by_node.get(
                        node.identifier
                    ),
                )
                for node in sorted(graph.nodes, key=lambda node: node.identifier)
            ],
            findings=[],
        )

    incoming_by_node: dict[str, float] = compute_node_incoming_rps(
        graph, scenario.workload
    )
    utilization_by_node: dict[str, float] = compute_node_utilization(graph, scenario)
    critical_path = compute_critical_path(graph, scenario)
    node_metrics, unavailable_latency_nodes = _build_node_metrics(
        graph,
        capacity_by_node,
        incoming_by_node,
        utilization_by_node,
        critical_path,
    )
    has_percentile_target: bool = any(
        isinstance(requirement, LatencyRequirement)
        for requirement in scenario.requirements
    )
    has_bounded_queues: bool = any(
        isinstance(node, CapacityNode) and incoming_by_node[node.identifier] > 0.0
        for node in graph.nodes
    )
    findings = sorted(
        _capacity_findings(graph, utilization_by_node),
        key=lambda finding: finding.affected_node_identifiers[0],
    )

    return PerformanceAnalysisReport(
        scenario_identifier=scenario.identifier,
        status=(
            PerformanceAnalysisStatus.PARTIAL
            if (
                unavailable_latency_nodes
                or has_bounded_queues
                or has_percentile_target
                or critical_path is None
                or critical_path.total_latency_ms is None
            )
            else PerformanceAnalysisStatus.COMPLETE
        ),
        nodes=sorted(node_metrics, key=lambda metric: metric.node_identifier),
        findings=findings,
        estimated_longest_synchronous_path_mean_milliseconds=(
            critical_path.total_latency_ms if critical_path is not None else None
        ),
        critical_path_node_identifiers=(
            list(critical_path.path_node_ids) if critical_path is not None else []
        ),
    )


def _build_node_metrics(
    graph: ArchitectureGraph,
    capacity_by_node: dict[str, float],
    incoming_by_node: dict[str, float],
    utilization_by_node: dict[str, float],
    critical_path: CriticalPathResult | None,
) -> tuple[list[NodePerformanceMetrics], list[str]]:
    """Build per-node metrics and collect nodes with unavailable latency."""
    node_metrics: list[NodePerformanceMetrics] = []
    unavailable_latency_nodes: list[str] = []

    for node in graph.nodes:
        response_time: float | None = (
            critical_path.node_latencies_ms.get(node.identifier)
            if critical_path is not None
            else None
        )
        queue_wait: float | None = (
            critical_path.node_queue_wait_ms.get(node.identifier)
            if critical_path is not None
            else None
        )

        if isinstance(node, CapacityNode):
            if response_time is None or not isfinite(response_time):
                response_time = None
                queue_wait = None
                unavailable_latency_nodes.append(node.identifier)
        else:
            response_time = None
            queue_wait = None

        node_metrics.append(
            NodePerformanceMetrics(
                node_identifier=node.identifier,
                incoming_requests_per_second=incoming_by_node[node.identifier],
                estimated_capacity_requests_per_second=capacity_by_node.get(
                    node.identifier
                ),
                utilization_ratio=utilization_by_node.get(node.identifier),
                estimated_mean_queue_wait_milliseconds=queue_wait,
                estimated_mean_response_time_milliseconds=response_time,
            )
        )

    return node_metrics, unavailable_latency_nodes


def _capacity_findings(
    graph: ArchitectureGraph,
    utilization_by_node: dict[str, float],
) -> list[PerformanceFinding]:
    """Create stable rule-based findings from existing utilization values."""
    findings: list[PerformanceFinding] = []

    for node in graph.nodes:
        if not isinstance(node, CapacityNode):
            continue

        utilization = utilization_by_node[node.identifier]
        if utilization >= SATURATION_THRESHOLD:
            findings.append(
                PerformanceFinding(
                    finding_code=PerformanceFindingCode.CAPACITY_SATURATION,
                    severity=PerformanceFindingSeverity.ERROR,
                    title="Узел приближается к пределу пропускной способности",
                    description=(
                        f"Расчётная загрузка узла {node.identifier} составляет "
                        f"{utilization:.1%} и достигает порога насыщения "
                        f"{SATURATION_THRESHOLD:.0%}."
                    ),
                    affected_node_identifiers=[node.identifier],
                    recommendation=(
                        "Проверьте возможность масштабирования узла или "
                        "изменения распределения нагрузки."
                    ),
                )
            )
    return findings
