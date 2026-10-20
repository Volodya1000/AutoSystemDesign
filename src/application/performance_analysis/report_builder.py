"""Build a performance report from existing domain calculations."""

from __future__ import annotations

from collections import Counter
from math import isfinite
from typing import TYPE_CHECKING

from domain.models.nodes import CapacityNode
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
from domain.specifications.latency_validator import compute_critical_path
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
    workload profile. Infinite latency estimates are represented as null,
    because the report contract intentionally accepts only finite numbers.
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
                for node in graph.nodes
            ],
            findings=[_workload_missing_finding()],
        )

    incoming_by_node: dict[str, float] = compute_node_incoming_rps(
        graph, scenario.workload
    )
    utilization_by_node: dict[str, float] = compute_node_utilization(graph, scenario)
    critical_path = compute_critical_path(graph, scenario)
    latency_by_node: dict[str, float] = (
        critical_path.node_latencies_ms if critical_path is not None else {}
    )

    node_metrics: list[NodePerformanceMetrics] = []
    nodes_with_unavailable_latency: list[str] = []

    for node in graph.nodes:
        response_time: float | None = latency_by_node.get(node.identifier)
        queue_wait: float | None = None

        if isinstance(node, CapacityNode):
            if response_time is not None and isfinite(response_time):
                queue_wait = max(
                    0.0,
                    response_time - node.mean_processing_time_milliseconds,
                )
            else:
                response_time = None
                nodes_with_unavailable_latency.append(node.identifier)
        else:
            response_time = None

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

    findings = _capacity_findings(graph, utilization_by_node)
    outgoing_edge_counts: Counter[str] = Counter(
        edge.source_identifier for edge in graph.edges
    )
    branching_nodes: list[str] = [
        node.identifier
        for node in graph.nodes
        if outgoing_edge_counts[node.identifier] > 1
    ]
    if branching_nodes:
        findings.append(_traffic_distribution_limitation(branching_nodes))
    if nodes_with_unavailable_latency:
        findings.append(_unavailable_latency_finding(nodes_with_unavailable_latency))

    status = (
        PerformanceAnalysisStatus.PARTIAL
        if nodes_with_unavailable_latency
        else PerformanceAnalysisStatus.COMPLETE
    )

    return PerformanceAnalysisReport(
        scenario_identifier=scenario.identifier,
        status=status,
        nodes=node_metrics,
        findings=findings,
    )


def _workload_missing_finding() -> PerformanceFinding:
    """Describe why load-dependent metrics are absent."""
    return PerformanceFinding(
        finding_code=PerformanceFindingCode.WORKLOAD_MISSING,
        severity=PerformanceFindingSeverity.WARNING,
        title="Недостаточно данных о нагрузке",
        description=(
            "Профиль нагрузки не задан, поэтому входящий поток, загрузку "
            "и оценку задержки рассчитать нельзя."
        ),
        recommendation="Задайте профиль нагрузки в сценарии.",
    )


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
        else:
            findings.append(
                PerformanceFinding(
                    finding_code=PerformanceFindingCode.CAPACITY_HEADROOM,
                    severity=PerformanceFindingSeverity.INFO,
                    title="Есть запас пропускной способности",
                    description=(
                        f"Расчётная загрузка узла {node.identifier} составляет "
                        f"{utilization:.1%}, что ниже порога насыщения "
                        f"{SATURATION_THRESHOLD:.0%}."
                    ),
                    affected_node_identifiers=[node.identifier],
                )
            )

    return findings


def _unavailable_latency_finding(
    node_identifiers: list[str],
) -> PerformanceFinding:
    """Explain why infinite latency estimates are omitted from finite JSON fields."""
    return PerformanceFinding(
        finding_code=PerformanceFindingCode.METRIC_UNAVAILABLE,
        severity=PerformanceFindingSeverity.WARNING,
        title="Оценка задержки недоступна как конечное значение",
        description=(
            "Расчётное время пребывания запроса в узлах "
            f"{', '.join(node_identifiers)} бесконечно при заданной нагрузке. "
            "Поля задержки оставлены null, поскольку контракт отчёта допускает "
            "только конечные числовые значения."
        ),
        affected_node_identifiers=node_identifiers,
    )


def _traffic_distribution_limitation(
    branching_node_identifiers: list[str],
) -> PerformanceFinding:
    """Describe the equal-split assumption where it affects branching nodes."""
    return PerformanceFinding(
        finding_code=PerformanceFindingCode.UNSUPPORTED_MODEL,
        severity=PerformanceFindingSeverity.WARNING,
        title="Допущение о распределении трафика",
        description=(
            "Исходящий поток равномерно распределяется между рёбрами узла. "
            "Текущая модель не выражает веса маршрутизации и кратность вызовов "
            "зависимостей; фактическая нагрузка на ветви может отличаться."
        ),
        affected_node_identifiers=branching_node_identifiers,
    )
