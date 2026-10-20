"""Build a performance report from existing domain calculations."""

from __future__ import annotations

from collections import Counter
from math import isfinite
from typing import TYPE_CHECKING

from domain.models.enums import EdgeRoutingMode
from domain.models.nodes import CacheNode, CapacityNode, DatabaseNode
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
    node_metrics, unavailable_latency_nodes = _build_node_metrics(
        graph,
        capacity_by_node,
        incoming_by_node,
        utilization_by_node,
        latency_by_node,
    )
    latency_slo_finding = _latency_slo_not_evaluated_finding(
        scenario,
        critical_path.path_node_ids
        if critical_path is not None and critical_path.total_latency_ms is not None
        else tuple(
            node.identifier for node in graph.nodes if isinstance(node, CapacityNode)
        ),
    )
    findings = _capacity_findings(graph, utilization_by_node)
    findings.extend(_branching_findings(graph))
    if latency_slo_finding is not None:
        findings.append(latency_slo_finding)
    if unavailable_latency_nodes:
        findings.append(_unavailable_latency_finding(unavailable_latency_nodes))

    return PerformanceAnalysisReport(
        scenario_identifier=scenario.identifier,
        status=(
            PerformanceAnalysisStatus.PARTIAL
            if unavailable_latency_nodes or latency_slo_finding is not None
            else PerformanceAnalysisStatus.COMPLETE
        ),
        nodes=node_metrics,
        findings=findings,
    )


def _build_node_metrics(
    graph: ArchitectureGraph,
    capacity_by_node: dict[str, float],
    incoming_by_node: dict[str, float],
    utilization_by_node: dict[str, float],
    latency_by_node: dict[str, float | None],
) -> tuple[list[NodePerformanceMetrics], list[str]]:
    """Build per-node metrics and collect nodes with unavailable latency."""
    node_metrics: list[NodePerformanceMetrics] = []
    unavailable_latency_nodes: list[str] = []

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
                unavailable_latency_nodes.append(node.identifier)
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

    return node_metrics, unavailable_latency_nodes


def _branching_findings(graph: ArchitectureGraph) -> list[PerformanceFinding]:
    """Report unresolved traffic distribution for alternative outgoing routes."""
    node_by_id = {node.identifier: node for node in graph.nodes}
    cache_reader_sources = {
        edge.source_identifier
        for edge in graph.edges
        if not edge.protocol.is_asynchronous
        and isinstance(node_by_id.get(edge.target_identifier), CacheNode)
    }
    alternative_edge_counts: Counter[str] = Counter(
        edge.source_identifier
        for edge in graph.edges
        if edge.routing_mode is EdgeRoutingMode.ALTERNATIVE
        and not (
            edge.source_identifier in cache_reader_sources
            and not edge.protocol.is_asynchronous
            and isinstance(node_by_id.get(edge.target_identifier), DatabaseNode)
        )
    )
    branching_nodes: list[str] = [
        node.identifier
        for node in graph.nodes
        if alternative_edge_counts[node.identifier] > 1
    ]
    if not branching_nodes:
        return []
    return [_traffic_distribution_limitation(branching_nodes)]


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


def _latency_slo_not_evaluated_finding(
    scenario: DesignScenario,
    critical_path_node_identifiers: tuple[str, ...],
) -> PerformanceFinding | None:
    """Explain that a percentile target cannot be checked from a mean estimate."""
    requirements = [
        requirement
        for requirement in scenario.requirements
        if isinstance(requirement, LatencyRequirement)
    ]
    if not requirements:
        return None

    targets = ", ".join(
        f"p{requirement.percentile:g} {requirement.operator.value} "
        f"{requirement.threshold_value:g} ms"
        for requirement in requirements
    )
    return PerformanceFinding(
        finding_code=PerformanceFindingCode.LATENCY_NOT_EVALUATED,
        severity=PerformanceFindingSeverity.WARNING,
        title="Процентильная цель задержки не оценена",
        description=(
            f"Цели {targets} нельзя проверить текущей моделью: она оценивает "
            "среднее время ответа, но не распределение задержки. Средняя оценка "
            "остаётся доступной отдельно и не интерпретируется как процентиль."
        ),
        affected_node_identifiers=list(critical_path_node_identifiers),
    )


def _unavailable_latency_finding(
    node_identifiers: list[str],
) -> PerformanceFinding:
    """Explain why infinite latency estimates are omitted from finite JSON fields."""
    return PerformanceFinding(
        finding_code=PerformanceFindingCode.METRIC_UNAVAILABLE,
        severity=PerformanceFindingSeverity.WARNING,
        title="Оценка задержки недоступна как конечное значение",
        description=(
            "Среднее время ответа не удалось оценить для указанных узлов. "
            "Текущая модель требует известного числа независимых каналов "
            "обслуживания, корректных параметров и устойчивого режима. "
            "Неоценённая задержка не означает нулевую задержку."
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
            "Трафик между альтернативными исходящими маршрутами распределяется "
            "поровну. Отдельные веса маршрутизации пока не задаются, поэтому "
            "фактическая нагрузка на эти маршруты может отличаться."
        ),
        affected_node_identifiers=branching_node_identifiers,
    )
