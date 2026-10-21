"""Aggregated metrics for the C4 diagram title."""

from __future__ import annotations

import math
from dataclasses import dataclass
from operator import itemgetter
from typing import TYPE_CHECKING

from domain.models.nodes import CapacityNode
from domain.models.requirements import BudgetRequirement, LatencyRequirement
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
    # Needed by format_metrics_title to render "computed/target ms".
    latency_sla_ms: float | None = None


def compute_project_metrics(
    graph: ArchitectureGraph,
    scenario: DesignScenario,
) -> ProjectMetrics:
    """Aggregate F3/F4/F5 outputs into a single immutable snapshot."""
    utilization = compute_node_utilization(graph, scenario) if scenario.workload else {}
    if utilization:
        max_node_id, max_utilization = max(
            utilization.items(), key=itemgetter(1)
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
    latency_slas = [
        float(req.threshold_value)
        for req in scenario.requirements
        if isinstance(req, LatencyRequirement)
    ]

    return ProjectMetrics(
        max_utilization=max_utilization,
        max_utilization_node_id=max_node_id,
        critical_path_latency_ms=critical_latency,
        total_monthly_cost_usd=total_cost,
        budget_limit_usd=min(budget_limits) if budget_limits else None,
        latency_sla_ms=min(latency_slas) if latency_slas else None,
    )


def format_metrics_title(metrics: ProjectMetrics) -> str:
    """Build a single-line summary for the C4 title.

    Example: 'Budget 2900/3000 USD | Peak util 67% | Path latency 245/300 ms'
    Omits any section whose data is absent.
    """
    parts: list[str] = []

    if metrics.budget_limit_usd is not None:
        parts.append(
            f"Budget {metrics.total_monthly_cost_usd:.0f}/"
            f"{metrics.budget_limit_usd:.0f} USD"
        )

    if metrics.max_utilization is not None:
        parts.append(f"Peak util {metrics.max_utilization * 100.0:.0f}%")

    if (
        metrics.critical_path_latency_ms is not None
        and metrics.latency_sla_ms is not None
    ):
        if math.isinf(metrics.critical_path_latency_ms):
            computed = "inf"
        else:
            computed = f"{metrics.critical_path_latency_ms:.0f}"
        parts.append(f"Path latency {computed}/{metrics.latency_sla_ms:.0f} ms")

    return " | ".join(parts)
