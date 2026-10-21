"""Calculate node capacity and validate estimated utilization.

Pure domain logic. The 98% threshold is an early-warning margin used by the
validator; mathematical queue instability occurs at 100% offered utilization.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.exceptions.architecture_errors import (
    ArchitectureValidationError,
    CapacitySaturationError,
)
from domain.models.nodes import CapacityNode
from domain.specifications.interfaces import ScenarioValidator, ValidationResult
from domain.specifications.traffic_flow import compute_node_incoming_rps

if TYPE_CHECKING:
    from domain.models.scenarios import DesignScenario
    from domain.models.topology import ArchitectureGraph

SATURATION_THRESHOLD: float = 0.98


def compute_node_capacity_rps(node: CapacityNode) -> float:
    """Calculate capacity from known service channels, else concurrency proxy."""
    independent_channels = node.queueing_server_count
    parallelism = (
        independent_channels
        if independent_channels is not None
        else node.replicas_count * node.maximum_concurrency
    )
    return parallelism * 1000.0 / node.mean_processing_time_milliseconds


def compute_node_utilization(
    graph: ArchitectureGraph,
    scenario: DesignScenario,
) -> dict[str, float]:
    """Return utilization ratio per capacity node.

    Utilization = incoming_rps / max_rps, where
    max_rps = parallelism * 1000 / mean_processing_time_ms.
    Parallelism is the explicit queueing server count when known; otherwise
    replicas_count * maximum_concurrency is a provisional capacity proxy.

    Client nodes are excluded. Nodes with zero incoming RPS are present with
    utilization 0.0. Returns an empty dict if scenario.workload is None.
    """
    if scenario.workload is None:
        return {}

    incoming = compute_node_incoming_rps(graph, scenario.workload)
    utilization: dict[str, float] = {}

    for node in graph.nodes:
        if not isinstance(node, CapacityNode):
            continue
        utilization[node.identifier] = incoming.get(
            node.identifier, 0.0
        ) / compute_node_capacity_rps(node)

    return utilization


class CapacitySaturationValidator(ScenarioValidator):
    """Reports CapacitySaturationError for every node above the threshold."""

    def validate(
        self,
        graph: ArchitectureGraph,
        scenario: DesignScenario,
    ) -> ValidationResult:
        if scenario.workload is None:
            return ValidationResult(errors=[])

        try:
            incoming = compute_node_incoming_rps(graph, scenario.workload)
        except ValueError:
            # Cycle detection is owned by StructuralTopologyValidator: the
            # aggregated ValidationResult already carries a
            # CyclicDependencyError for this graph. Skipping the workload
            # computation here avoids crashing the repair loop and lets the
            # structural error reach the model as actionable feedback.
            return ValidationResult(errors=[])

        errors: list[ArchitectureValidationError] = []
        for node in graph.nodes:
            if not isinstance(node, CapacityNode):
                continue

            max_rps = compute_node_capacity_rps(node)
            arrival_rps = incoming.get(node.identifier, 0.0)
            utilization = arrival_rps / max_rps

            if utilization >= SATURATION_THRESHOLD:
                errors.append(
                    CapacitySaturationError(
                        node_identifier=node.identifier,
                        utilization_percentage=utilization * 100.0,
                        arrival_rate_rps=arrival_rps,
                        maximum_capacity_rps=max_rps,
                    )
                )

        return ValidationResult(errors=errors)
