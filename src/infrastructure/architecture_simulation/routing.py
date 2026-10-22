"""Resolve stable single-request paths for alternative edges and cache misses."""

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
    """Select a single route, treating compute-owned DB edges as miss fallbacks."""

    def validate(self, plan: GraphSimulationPlan) -> None:
        """Reject unsupported branches and cache topology before any simulation."""
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
            self._validate_outgoing(source_identifier, outgoing, positions, resources)
        self._validate_cache_contract(edges, resources)

    @staticmethod
    def _validate_outgoing(
        source_identifier: str,
        outgoing: list[SimulatedConnection],
        positions: dict[str, int],
        resources: dict[str, SimulatedResource],
    ) -> None:
        """Check that all physical graph edges are ordered and supported."""
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
                    GraphExecutionFailure.BRANCHING_UNSUPPORTED, source_identifier
                )
            if edge.target_identifier not in resources:
                raise GraphExecutionError(
                    GraphExecutionFailure.UNKNOWN_RESOURCE, edge.target_identifier
                )

    @staticmethod
    def _validate_cache_contract(
        edges: dict[str, list[SimulatedConnection]],
        resources: dict[str, SimulatedResource],
    ) -> None:
        """Require one lookup per compute reader and explicit sibling DB fallback."""
        read_caches: set[str] = set()
        source_identifier: str
        outgoing: list[SimulatedConnection]
        for source_identifier, outgoing in edges.items():
            lookups: list[SimulatedConnection] = [
                edge
                for edge in outgoing
                if resources[edge.target_identifier].node_type == NodeType.CACHE
            ]
            if not lookups:
                continue
            source: SimulatedResource | None = resources.get(source_identifier)
            if (
                source is None
                or source.node_type != NodeType.COMPUTE
                or len(lookups) != 1
                or not any(
                    resources[edge.target_identifier].node_type == NodeType.DATABASE
                    for edge in outgoing
                )
            ):
                raise GraphExecutionError(
                    GraphExecutionFailure.INVALID_CACHE_TOPOLOGY, source_identifier
                )
            read_caches.add(lookups[0].target_identifier)

        resource: SimulatedResource
        for resource in resources.values():
            if resource.node_type != NodeType.CACHE:
                continue
            if (
                resource.cache_hit_probability is None
                or resource.identifier not in read_caches
                or resource.identifier in edges
            ):
                raise GraphExecutionError(
                    GraphExecutionFailure.INVALID_CACHE_TOPOLOGY,
                    resource.identifier,
                )

    def select(
        self, plan: GraphSimulationPlan, seed: int, request_index: int
    ) -> list[tuple[SimulatedConnection, SimulatedResource]]:
        """Route a cache miss via the original compute reader's database edge."""
        edges: dict[str, list[SimulatedConnection]] = self._group_edges(plan)
        resources: dict[str, SimulatedResource] = {
            resource.identifier: resource for resource in plan.resources
        }
        current: str = plan.client_identifier
        route: list[tuple[SimulatedConnection, SimulatedResource]] = []
        while current in edges:
            outgoing: list[SimulatedConnection] = edges[current]
            cache_lookups: list[SimulatedConnection] = [
                edge
                for edge in outgoing
                if resources[edge.target_identifier].node_type == NodeType.CACHE
            ]
            fallback_edges: list[SimulatedConnection] = [
                edge
                for edge in outgoing
                if cache_lookups
                and resources[edge.target_identifier].node_type == NodeType.DATABASE
            ]
            primary_edges: list[SimulatedConnection] = [
                edge for edge in outgoing if edge not in fallback_edges
            ]
            choice: SimulatedConnection = self._choose(
                primary_edges, seed, request_index, current, "route"
            )
            resource: SimulatedResource = resources[choice.target_identifier]
            route.append((choice, resource))
            if resource.node_type == NodeType.CACHE:
                hits: Random = Random(
                    f"{seed}:cache:{request_index}:{resource.identifier}"
                )
                probability: float = resource.cache_hit_probability or 0.0
                if hits.random() < probability:
                    break
                fallback: SimulatedConnection = self._choose(
                    fallback_edges, seed, request_index, current, "fallback"
                )
                route.append((fallback, resources[fallback.target_identifier]))
                current = fallback.target_identifier
            else:
                current = resource.identifier
        return route

    @staticmethod
    def _choose(
        outgoing: list[SimulatedConnection],
        seed: int,
        request_index: int,
        source_identifier: str,
        decision: str,
    ) -> SimulatedConnection:
        """Choose uniformly with a stable seed independent of input ordering."""
        rng: Random = Random(f"{seed}:{decision}:{request_index}:{source_identifier}")
        return outgoing[rng.randrange(len(outgoing))]

    @staticmethod
    def _group_edges(
        plan: GraphSimulationPlan,
    ) -> dict[str, list[SimulatedConnection]]:
        """Group physical edges in an order independent of JSON serialization."""
        edges: dict[str, list[SimulatedConnection]] = {}
        edge: SimulatedConnection
        for edge in plan.connections:
            edges.setdefault(edge.source_identifier, []).append(edge)
        outgoing: list[SimulatedConnection]
        for outgoing in edges.values():
            outgoing.sort(key=lambda connection: connection.target_identifier)
        return edges
