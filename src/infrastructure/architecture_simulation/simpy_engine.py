"""Execute FIFO single-node request traces with SimPy virtual time."""

from collections.abc import Generator

import simpy

from domain.architecture_simulation.kernel import (
    CompletedRequestObservation,
    ScheduledRequest,
    SimulationWindow,
    SingleNodeSimulationPlan,
    SingleNodeSimulationResult,
    WindowSimulationResult,
)
from infrastructure.architecture_simulation.horizon import run_simulation_until_horizon


class SimPySingleNodeEngine:
    """Simulate a resource with one or more identical FIFO channels."""

    def simulate(self, plan: SingleNodeSimulationPlan) -> SingleNodeSimulationResult:
        """Drain a deterministic schedule and preserve its original order."""
        environment, completed = self._prepare(plan)
        environment.run()
        observations: list[CompletedRequestObservation] = [
            completed[index] for index in range(len(plan.requests))
        ]
        return SingleNodeSimulationResult(observations=observations)

    def simulate_window(
        self, plan: SingleNodeSimulationPlan, window: SimulationWindow
    ) -> WindowSimulationResult:
        """End before the horizon and retain censored measured requests."""
        environment, completed = self._prepare(plan)
        run_simulation_until_horizon(environment, window)

        indices: list[int] = [
            index
            for index, request in enumerate(plan.requests)
            if window.warmup_seconds <= request.arrival_seconds < window.horizon_seconds
        ]
        observations: list[CompletedRequestObservation] = [
            completed[index] for index in indices if index in completed
        ]
        warmup_arrivals: int = sum(
            request.arrival_seconds < window.warmup_seconds for request in plan.requests
        )
        return WindowSimulationResult(
            observations=observations,
            measured_arrivals=len(indices),
            unfinished=len(indices) - len(observations),
            warmup_arrivals=warmup_arrivals,
        )

    def _prepare(
        self, plan: SingleNodeSimulationPlan
    ) -> tuple[simpy.Environment, dict[int, CompletedRequestObservation]]:
        """Schedule all input arrivals in a fresh SimPy environment."""
        environment: simpy.Environment = simpy.Environment()
        resource: simpy.Resource = simpy.Resource(
            environment, capacity=plan.service_channels
        )
        completed: dict[int, CompletedRequestObservation] = {}
        index: int
        request: ScheduledRequest
        for index, request in enumerate(plan.requests):
            environment.process(
                self._serve(environment, resource, index, request, completed)
            )
        return environment, completed

    @staticmethod
    def _serve(
        environment: simpy.Environment,
        resource: simpy.Resource,
        request_index: int,
        request: ScheduledRequest,
        completed: dict[int, CompletedRequestObservation],
    ) -> Generator[simpy.events.Event]:
        """Wait for arrival, acquire one channel, serve, and release it."""
        yield environment.timeout(request.arrival_seconds)
        arrival: float = environment.now

        admission: simpy.resources.resource.Request = resource.request()
        with admission:
            yield admission
            started: float = environment.now
            yield environment.timeout(request.service_seconds)

        observation: CompletedRequestObservation = CompletedRequestObservation(
            request_index=request_index,
            arrival_seconds=arrival,
            service_start_seconds=started,
            completion_seconds=environment.now,
        )
        completed[request_index] = observation
