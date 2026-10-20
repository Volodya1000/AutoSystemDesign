"""Project-level metrics used in generated diagram titles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from domain.models.nodes import CapacityNode
from domain.models.topology import ArchitectureGraph
from domain.specifications.latency_validator import compute_critical_path
from domain.specifications.traffic_flow import compute_node_utilization

if TYPE_CHECKING:
    from domain.models.scenarios import DesignScenario


@dataclass(frozen=True)
class ProjectMetrics:
    """Summary metrics shown in architecture diagram titles."""

    max_utilization_ratio: float | None
    critical_path_latency_ms: float | None
    total_monthly_cost_usd: float
    budget_limit_usd: float | None


def compute_project_metrics(
    graph: ArchitectureGraph,
    scenario: DesignScenario,
) -> ProjectMetrics:
    """Compute project metrics without treating mean latency as a percentile SLO."""
    utilization_by_node = compute_node_utilization(graph, scenario.workload)
    max_utilization = max(utilization_by_node.values(), default=None)

    critical_path = compute_critical_path(graph, scenario)
    critical_latency = (
        None if critical_path is None else critical_path.total_latency_ms
    )

    total_cost = sum(
        node.monthly_cost_usd for node in graph.nodes if isinstance(node, CapacityNode)
    )

    return ProjectMetrics(
        max_utilization_ratio=max_utilization,
        critical_path_latency_ms=critical_latency,
        total_monthly_cost_usd=total_cost,
        budget_limit_usd=scenario.budget_limit_usd,
    )


def format_metrics_title(metrics: ProjectMetrics) -> str:
    """Format metrics for a diagram title without comparing mean to p95/p99."""
    parts: list[str] = []
    if metrics.max_utilization_ratio is not None:
        parts.append(f"Max util {metrics.max_utilization_ratio:.0%}")
    if metrics.critical_path_latency_ms is not None:
        parts.append(f"Path mean {metrics.critical_path_latency_ms:.0f} ms")
    parts.append(f"Cost ${metrics.total_monthly_cost_usd:.0f}/mo")
    if metrics.budget_limit_usd is not None:
        parts.append(f"Budget ${metrics.budget_limit_usd:.0f}/mo")
    return " | ".join(parts)
