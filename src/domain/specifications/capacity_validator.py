"""Capacity utilization: nodes must not exceed the saturation threshold.

Pure module. The 98% threshold is hardcoded by the roadmap (F4): a node at
or above it has an infinite queue and will collapse at peak load.
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


def _node_max_rps(node: CapacityNode) -> float:
    """Maximum processing rate of one capacity node, requests/sec."""
    return (
        node.replicas_count
        * node.maximum_concurrency
        * 1000.0
        / node.mean_processing_time_milliseconds
    )


def compute_node_utilization(
    graph: ArchitectureGraph,
    scenario: DesignScenario,
) -> dict[str, float]:
    """Returns utilization ratio per capacity node.

    Utilization = incoming_rps / max_rps, where
    max_rps = replicas_count * maximum_concurrency * 1000 / mean_processing_time_ms.

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
        ) / _node_max_rps(node)

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

            max_rps = _node_max_rps(node)
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
