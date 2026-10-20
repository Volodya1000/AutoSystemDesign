"""Build a user-facing report from existing performance calculations."""

from __future__ import annotations

from collections import Counter

from domain.models.nodes import CapacityNode
from domain.models.scenarios import DesignScenario
from domain.models.topology import ArchitectureGraph
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
from domain.specifications.traffic_flow import compute_node_incoming_rps


def build_performance_analysis_report(
    graph: ArchitectureGraph,
    scenario: DesignScenario,
) -> PerformanceAnalysisReport:
    """Build capacity metrics without introducing a second calculation model.

    The report currently evaluates incoming traffic, modelled capacity, and
    utilization. Queue waiting time and response time stay unknown until a
    separately validated queueing model is introduced.
    """
    if scenario.workload is None:
        return _build_unavailable_report(graph, scenario)

    incoming_by_node = compute_node_incoming_rps(graph, scenario.workload)
    utilization_by_node = compute_node_utilization(graph, scenario)
    capacity_by_node = {
        node.identifier: compute_node_capacity_rps(node)
        for node in graph.nodes
        if isinstance(node, CapacityNode)
    }

    node_metrics = [
        NodePerformanceMetrics(
            node_identifier=node.identifier,
            incoming_requests_per_second=incoming_by_node[node.identifier],
            estimated_capacity_requests_per_second=capacity_by_node.get(
                node.identifier
            ),
            utilization_ratio=utilization_by_node.get(node.identifier),
        )
        for node in graph.nodes
    ]

    findings = _capacity_findings(
        graph, incoming_by_node, utilization_by_node, capacity_by_node
    )
    findings.append(_latency_not_evaluated_finding())

    outgoing_edge_counts = Counter(edge.source_identifier for edge in graph.edges)
    branching_nodes = [
        node.identifier
        for node in graph.nodes
        if outgoing_edge_counts[node.identifier] > 1
    ]
    if branching_nodes:
        findings.append(_traffic_distribution_limitation(branching_nodes))

    return PerformanceAnalysisReport(
        scenario_identifier=scenario.identifier,
        status=PerformanceAnalysisStatus.PARTIAL,
        nodes=node_metrics,
        findings=findings,
    )


def _build_unavailable_report(
    graph: ArchitectureGraph,
    scenario: DesignScenario,
) -> PerformanceAnalysisReport:
    """Retain only static capacities when load-dependent metrics are unknown."""
    node_metrics = [
        NodePerformanceMetrics(
            node_identifier=node.identifier,
            estimated_capacity_requests_per_second=(
                compute_node_capacity_rps(node)
                if isinstance(node, CapacityNode)
                else None
            ),
        )
        for node in graph.nodes
    ]
    return PerformanceAnalysisReport(
        scenario_identifier=scenario.identifier,
        status=PerformanceAnalysisStatus.UNAVAILABLE,
        nodes=node_metrics,
        findings=[_workload_missing_finding()],
    )


def _capacity_findings(
    graph: ArchitectureGraph,
    incoming_by_node: dict[str, float],
    utilization_by_node: dict[str, float],
    capacity_by_node: dict[str, float],
) -> list[PerformanceFinding]:
    """Create one actionable finding for each node reaching the existing limit."""
    findings: list[PerformanceFinding] = []
    for node in graph.nodes:
        utilization = utilization_by_node.get(node.identifier)
        capacity = capacity_by_node.get(node.identifier)
        if utilization is None or capacity is None:
            continue
        if utilization < SATURATION_THRESHOLD:
            continue

        incoming_rps = incoming_by_node[node.identifier]
        findings.append(
            PerformanceFinding(
                finding_code=PerformanceFindingCode.CAPACITY_SATURATION,
                severity=PerformanceFindingSeverity.ERROR,
                title="Риск насыщения пропускной способности",
                description=(
                    f"Расчётная нагрузка узла {node.identifier} составляет "
                    f"{incoming_rps:.1f} запросов/с при расчётной пропускной "
                    f"способности {capacity:.1f} запросов/с "
                    f"(загрузка {utilization * 100.0:.1f}%). "
                    f"Порог текущего валидатора — "
                    f"{SATURATION_THRESHOLD * 100.0:.0f}%."
                ),
                affected_node_identifiers=[node.identifier],
                recommendation=(
                    "Проверьте параметры пропускной способности узла и "
                    "рассмотрите масштабирование компонента или снижение нагрузки."
                ),
            )
        )
    return findings


def _workload_missing_finding() -> PerformanceFinding:
    """Explain why load-dependent metrics are unavailable."""
    return PerformanceFinding(
        finding_code=PerformanceFindingCode.WORKLOAD_MISSING,
        severity=PerformanceFindingSeverity.WARNING,
        title="Недостаточно данных о нагрузке",
        description=(
            "В сценарии не задан профиль нагрузки, поэтому входящий поток и "
            "загрузка узлов не рассчитываются. Статическая пропускная способность "
            "узлов остаётся доступной."
        ),
        recommendation="Укажите профиль нагрузки в YAML-сценарии.",
    )


def _latency_not_evaluated_finding() -> PerformanceFinding:
    """Make intentionally deferred latency metrics explicit."""
    return PerformanceFinding(
        finding_code=PerformanceFindingCode.LATENCY_NOT_EVALUATED,
        severity=PerformanceFindingSeverity.INFO,
        title="Задержка не оценивалась",
        description=(
            "Этот этап формирует метрики нагрузки и пропускной способности. "
            "Среднее ожидание в очереди и время ответа не заполняются, пока "
            "модель очереди не будет отдельно проверена."
        ),
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
