"""Execute a forward-only linear C4 chain with explicit SimPy resources."""

from collections.abc import Generator
from dataclasses import dataclass
from random import Random

import simpy

from application.architecture_simulation.graph_execution_errors import (
    GraphExecutionError,
    GraphExecutionFailure,
)
from domain.architecture_simulation.graph_execution import (
    GraphRejectionReason,
    GraphRequestRejection,
    GraphRequestTrace,
    GraphTraceWindowResult,
    GraphTraversalObservation,
)
from domain.architecture_simulation.graph_plan import (
    GraphSimulationPlan,
    SimulatedConnection,
    SimulatedResource,
)
from domain.architecture_simulation.kernel import SimulationWindow
from domain.models.enums import NodeType
from infrastructure.architecture_simulation.admission import rejection_reason
from infrastructure.architecture_simulation.horizon import run_simulation_until_horizon


@dataclass(slots=True)
class _LinearRuntime:
    """Carry one isolated SimPy experiment's services and progress."""

    environment: simpy.Environment
    route: list[tuple[SimulatedConnection, SimulatedResource]]
    node_resources: dict[str, list[simpy.Resource]]
    service_rng: dict[str, Random]
    next_replica: dict[str, int]
    completed: dict[int, GraphTraversalObservation]
    rejections: dict[int, GraphRequestRejection]


class SimPyLinearGraphEngine:
    """Simulate a linear request chain without pretending to support fan-out."""

    def simulate(
        self, trace: GraphRequestTrace, window: SimulationWindow
    ) -> GraphTraceWindowResult:
        """Run events up to but not including the end of the measured horizon."""
        route: list[tuple[SimulatedConnection, SimulatedResource]] = (
            self._resolve_linear_route(trace.plan)
        )
        environment: simpy.Environment = simpy.Environment()
        node_resources: dict[str, list[simpy.Resource]] = {
            resource.identifier: [
                simpy.Resource(
                    environment,
                    capacity=resource.service_channels_per_replica,
                )
                for _ in range(resource.replicas_count)
            ]
            for resource in trace.plan.resources
        }
        service_rng: dict[str, Random] = {
            resource.identifier: Random(f"{trace.seed}:{resource.identifier}")
            for resource in trace.plan.resources
        }
        next_replica: dict[str, int] = {
            resource.identifier: 0 for resource in trace.plan.resources
        }
        completed: dict[int, GraphTraversalObservation] = {}
        rejections: dict[int, GraphRequestRejection] = {}
        runtime: _LinearRuntime = _LinearRuntime(
            environment=environment,
            route=route,
            node_resources=node_resources,
            service_rng=service_rng,
            next_replica=next_replica,
            completed=completed,
            rejections=rejections,
        )
        arrival_index: int
        arrival_seconds: float
        for arrival_index, arrival_seconds in enumerate(trace.arrival_times_seconds):
            if arrival_seconds >= window.horizon_seconds:
                continue
            environment.process(self._traverse(runtime, arrival_index, arrival_seconds))

        run_simulation_until_horizon(environment, window)

        measured_indices: list[int] = [
            index
            for index, arrival in enumerate(trace.arrival_times_seconds)
            if window.warmup_seconds <= arrival < window.horizon_seconds
        ]
        observations: list[GraphTraversalObservation] = [
            completed[index] for index in measured_indices if index in completed
        ]
        rejected: list[GraphRequestRejection] = [
            rejections[index] for index in measured_indices if index in rejections
        ]
        warmup_arrivals: int = sum(
            arrival < window.warmup_seconds for arrival in trace.arrival_times_seconds
        )
        return GraphTraceWindowResult(
            observations=observations,
            rejections=rejected,
            measured_arrivals=len(measured_indices),
            unfinished=len(measured_indices) - len(observations) - len(rejected),
            warmup_arrivals=warmup_arrivals,
        )

    def _resolve_linear_route(
        self, plan: GraphSimulationPlan
    ) -> list[tuple[SimulatedConnection, SimulatedResource]]:
        """Reject branching and resolve an ordered client-to-sink path."""
        by_source: dict[str, list[SimulatedConnection]] = {}
        edge: SimulatedConnection
        for edge in plan.connections:
            by_source.setdefault(edge.source_identifier, []).append(edge)

        resource_by_identifier: dict[str, SimulatedResource] = {
            resource.identifier: resource for resource in plan.resources
        }
        current: str = plan.client_identifier
        route: list[tuple[SimulatedConnection, SimulatedResource]] = []
        traversed: set[str] = set()
        while current in by_source:
            if current in traversed or len(by_source[current]) != 1:
                raise GraphExecutionError(
                    GraphExecutionFailure.BRANCHING_UNSUPPORTED, current
                )
            traversed.add(current)
            edge = by_source[current][0]
            resource: SimulatedResource | None = resource_by_identifier.get(
                edge.target_identifier
            )
            if resource is None:
                raise GraphExecutionError(
                    GraphExecutionFailure.UNKNOWN_RESOURCE,
                    edge.target_identifier,
                )
            if resource.node_type == NodeType.CACHE:
                raise GraphExecutionError(
                    GraphExecutionFailure.CACHE_UNSUPPORTED, resource.identifier
                )
            route.append((edge, resource))
            current = resource.identifier
        if len(route) != len(plan.resources):
            raise GraphExecutionError(
                GraphExecutionFailure.BRANCHING_UNSUPPORTED, current
            )
        return route

    def _traverse(
        self,
        runtime: _LinearRuntime,
        request_index: int,
        arrival_seconds: float,
    ) -> Generator[simpy.events.Event]:
        """Visit each resource with network delays and deterministic replica choice."""
        yield runtime.environment.timeout(arrival_seconds)
        visited: list[str] = []
        edge: SimulatedConnection
        resource: SimulatedResource
        for edge, resource in runtime.route:
            yield runtime.environment.timeout(edge.network_latency_seconds)
            replicas: list[simpy.Resource] = runtime.node_resources[resource.identifier]
            replica_index: int = runtime.next_replica[resource.identifier] % len(
                replicas
            )
            runtime.next_replica[resource.identifier] += 1
            reason: GraphRejectionReason | None = rejection_reason(
                replicas[replica_index], resource
            )
            if reason is not None:
                runtime.rejections[request_index] = GraphRequestRejection(
                    request_index=request_index,
                    node_identifier=resource.identifier,
                    replica_index=replica_index,
                    at_seconds=float(runtime.environment.now),
                    reason_code=reason,
                )
                return
            admission: simpy.resources.resource.Request = replicas[
                replica_index
            ].request()
            with admission:
                yield admission
                service_seconds: float = self._sample_service(
                    resource, runtime.service_rng[resource.identifier]
                )
                yield runtime.environment.timeout(service_seconds)
            visited.append(resource.identifier)
        runtime.completed[request_index] = GraphTraversalObservation(
            request_index=request_index,
            arrival_seconds=arrival_seconds,
            completion_seconds=float(runtime.environment.now),
            visited_resources=visited,
        )

    @staticmethod
    def _sample_service(resource: SimulatedResource, rng: Random) -> float:
        """Sample a Gamma service duration or use the constant mean."""
        if resource.std_service_seconds == 0.0:
            return resource.mean_service_seconds
        shape: float = (
            resource.mean_service_seconds / resource.std_service_seconds
        ) ** 2
        scale: float = resource.std_service_seconds**2 / resource.mean_service_seconds
        service_seconds: float = rng.gammavariate(shape, scale)
        if service_seconds <= 0:
            message: str = "Gamma service duration must be positive"
            raise ValueError(message)
        return service_seconds
