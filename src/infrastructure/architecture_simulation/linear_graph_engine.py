"""Execute reproducible single-path C4 request traces with SimPy."""

from collections.abc import Generator
from dataclasses import dataclass
from random import Random

import simpy

from domain.architecture_simulation.graph_execution import (
    GraphRejectionReason,
    GraphRequestRejection,
    GraphRequestTrace,
    GraphTraceWindowResult,
    GraphTraversalObservation,
)
from domain.architecture_simulation.graph_plan import (
    SimulatedConnection,
    SimulatedResource,
)
from domain.architecture_simulation.kernel import SimulationWindow
from infrastructure.architecture_simulation.admission import rejection_reason
from infrastructure.architecture_simulation.horizon import run_simulation_until_horizon
from infrastructure.architecture_simulation.routing import StochasticRouteSelector


@dataclass(slots=True)
class _LinearRuntime:
    """Carry one isolated SimPy experiment's services and progress."""

    environment: simpy.Environment
    routes: dict[int, list[tuple[SimulatedConnection, SimulatedResource]]]
    node_resources: dict[str, list[simpy.Resource]]
    service_rng: dict[str, Random]
    next_replica: dict[str, int]
    completed: dict[int, GraphTraversalObservation]
    rejections: dict[int, GraphRequestRejection]


class SimPyLinearGraphEngine:
    """Simulate one selected route per request with bounded per-replica queues."""

    def simulate(
        self, trace: GraphRequestTrace, window: SimulationWindow
    ) -> GraphTraceWindowResult:
        """Simulate independent root routes up to the observation horizon."""
        routing: StochasticRouteSelector = StochasticRouteSelector()
        routing.validate(trace.plan)
        runtime: _LinearRuntime = self._prepare_runtime(trace)
        request_index: int
        arrival_seconds: float
        for request_index, arrival_seconds in enumerate(trace.arrival_times_seconds):
            if arrival_seconds >= window.horizon_seconds:
                continue
            runtime.routes[request_index] = routing.select(
                trace.plan, trace.seed, request_index
            )
            runtime.environment.process(
                self._traverse(runtime, request_index, arrival_seconds)
            )

        run_simulation_until_horizon(runtime.environment, window)
        return self._collect_window(trace, window, runtime)

    @staticmethod
    def _prepare_runtime(trace: GraphRequestTrace) -> _LinearRuntime:
        """Allocate a fresh set of resources and independent per-node RNGs."""
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
        return _LinearRuntime(
            environment=environment,
            routes={},
            node_resources=node_resources,
            service_rng=service_rng,
            next_replica=next_replica,
            completed={},
            rejections={},
        )

    @staticmethod
    def _collect_window(
        trace: GraphRequestTrace,
        window: SimulationWindow,
        runtime: _LinearRuntime,
    ) -> GraphTraceWindowResult:
        """Account for completed, rejected and censored measured root requests."""
        measured_indices: list[int] = [
            index
            for index, arrival in enumerate(trace.arrival_times_seconds)
            if window.warmup_seconds <= arrival < window.horizon_seconds
        ]
        observations: list[GraphTraversalObservation] = [
            runtime.completed[index]
            for index in measured_indices
            if index in runtime.completed
        ]
        rejected: list[GraphRequestRejection] = [
            runtime.rejections[index]
            for index in measured_indices
            if index in runtime.rejections
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
        for edge, resource in runtime.routes[request_index]:
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
