"""Aggregated metrics for the C4 diagram title."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain.models.nodes import CapacityNode
from domain.models.requirements import BudgetRequirement
from domain.specifications.capacity_validator import compute_node_utilization
from domain.specifications.latency_validator import compute_critical_path

if TYPE_CHECKING:
    from domain.models.scenarios import DesignScenario
    from domain.models.topology import ArchitectureGraph


@dataclass(frozen=True)
class ProjectMetrics:
    max_utilization: float | None
    max_utilization_node_id: str | None
    critical_path_latency_ms: float | None
    total_monthly_cost_usd: float
    budget_limit_usd: float | None


def compute_project_metrics(
    graph: ArchitectureGraph,
    scenario: DesignScenario,
) -> ProjectMetrics:
    """Aggregate capacity, mean latency, and cost without percentile comparisons."""
    utilization = compute_node_utilization(graph, scenario) if scenario.workload else {}
    if utilization:
        max_node_id, max_utilization = max(
            utilization.items(), key=lambda item: item[1]
        )
    else:
        max_node_id = None
        max_utilization = None

    critical = compute_critical_path(graph, scenario) if scenario.workload else None
    critical_latency = critical.total_latency_ms if critical is not None else None
    total_cost = sum(
        float(node.monthly_cost_usd)
        for node in graph.nodes
        if isinstance(node, CapacityNode)
    )
    budget_limits = [
        float(req.threshold_value)
        for req in scenario.requirements
        if isinstance(req, BudgetRequirement)
    ]

    return ProjectMetrics(
        max_utilization=max_utilization,
        max_utilization_node_id=max_node_id,
        critical_path_latency_ms=critical_latency,
        total_monthly_cost_usd=total_cost,
        budget_limit_usd=min(budget_limits) if budget_limits else None,
    )


def format_metrics_title(metrics: ProjectMetrics) -> str:
    """Build a title that labels latency as a mean, not a percentile SLO."""
    parts: list[str] = []
    if metrics.budget_limit_usd is not None:
        parts.append(
            f"Budget {metrics.total_monthly_cost_usd:.0f}/"
            f"{metrics.budget_limit_usd:.0f} USD"
        )
    if metrics.max_utilization is not None:
        parts.append(f"Peak util {metrics.max_utilization * 100.0:.0f}%")
    if metrics.critical_path_latency_ms is not None:
        parts.append(f"Path mean {metrics.critical_path_latency_ms:.0f} ms")
    return " | ".join(parts)
