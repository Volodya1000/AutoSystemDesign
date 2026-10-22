"""Resolve a reproducible single synchronous path through alternative/cache DAGs."""

from random import Random

from application.architecture_simulation.graph_execution_errors import (
    GraphExecutionError,
    GraphExecutionFailure,
)
from domain.architecture_simulation.graph_plan import (
    GraphSimulationPlan,
    SimulatedConnection,
    SimulatedResource,
)
from domain.models.enums import EdgeRoutingMode, NodeType


class StochasticRouteSelector:
    """Select one alternative edge per call and one cache outcome per request."""

    def validate(self, plan: GraphSimulationPlan) -> None:
        """Reject ambiguous fan-out and malformed cache miss destinations."""
        positions: dict[str, int] = {
            identifier: index for index, identifier in enumerate(plan.topological_order)
        }
        edges: dict[str, list[SimulatedConnection]] = self._group_edges(plan)
        resources: dict[str, SimulatedResource] = {
            resource.identifier: resource for resource in plan.resources
        }
        source_identifier: str
        outgoing: list[SimulatedConnection]
        for source_identifier, outgoing in edges.items():
            if any(edge.routing_mode == EdgeRoutingMode.FAN_OUT for edge in outgoing):
                raise GraphExecutionError(
                    GraphExecutionFailure.BRANCHING_UNSUPPORTED, source_identifier
                )
            if len({edge.routing_mode for edge in outgoing}) != 1:
                raise GraphExecutionError(
                    GraphExecutionFailure.MIXED_ROUTING_MODES, source_identifier
                )
            for edge in outgoing:
                if (
                    edge.source_identifier not in positions
                    or edge.target_identifier not in positions
                    or positions[edge.source_identifier]
                    >= positions[edge.target_identifier]
                ):
                    raise GraphExecutionError(
                        GraphExecutionFailure.BRANCHING_UNSUPPORTED,
                        source_identifier,
                    )
                if edge.target_identifier not in resources:
                    raise GraphExecutionError(
                        GraphExecutionFailure.UNKNOWN_RESOURCE,
                        edge.target_identifier,
                    )
        resource: SimulatedResource
        for resource in plan.resources:
            if resource.node_type != NodeType.CACHE:
                continue
            successors: list[SimulatedConnection] = edges.get(resource.identifier, [])
            if (
                resource.cache_hit_probability is None
                or len(successors) != 1
                or resources[successors[0].target_identifier].node_type
                != NodeType.DATABASE
            ):
                raise GraphExecutionError(
                    GraphExecutionFailure.INVALID_CACHE_TOPOLOGY,
                    resource.identifier,
                )

    def select(
        self, plan: GraphSimulationPlan, seed: int, request_index: int
    ) -> list[tuple[SimulatedConnection, SimulatedResource]]:
        """Draw one route independently of traversal order and queue timings."""
        edges: dict[str, list[SimulatedConnection]] = self._group_edges(plan)
        resources: dict[str, SimulatedResource] = {
            resource.identifier: resource for resource in plan.resources
        }
        current: str = plan.client_identifier
        route: list[tuple[SimulatedConnection, SimulatedResource]] = []
        while current in edges:
            outgoing: list[SimulatedConnection] = edges[current]
            rng: Random = Random(f"{seed}:route:{request_index}:{current}")
            choice: SimulatedConnection = outgoing[rng.randrange(len(outgoing))]
            resource: SimulatedResource = resources[choice.target_identifier]
            route.append((choice, resource))
            if resource.node_type == NodeType.CACHE:
                hits: Random = Random(
                    f"{seed}:cache:{request_index}:{resource.identifier}"
                )
                probability: float = resource.cache_hit_probability or 0.0
                if hits.random() < probability:
                    break
            current = resource.identifier
        return route

    @staticmethod
    def _group_edges(
        plan: GraphSimulationPlan,
    ) -> dict[str, list[SimulatedConnection]]:
        """Group connections in a stable input-order-independent order."""
        edges: dict[str, list[SimulatedConnection]] = {}
        edge: SimulatedConnection
        for edge in plan.connections:
            edges.setdefault(edge.source_identifier, []).append(edge)
        outgoing: list[SimulatedConnection]
        for outgoing in edges.values():
            outgoing.sort(key=lambda connection: connection.target_identifier)
        return edges
