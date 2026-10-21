"""Execute a single-node request trace in SimPy's virtual time.

This adapter owns SimPy resources and scheduling. All inputs and observations
remain independent of SimPy, so future routing and statistics can use them
without leaking the simulation framework into the domain.
"""

from collections.abc import Generator

import simpy

from domain.architecture_simulation.kernel import (
    CompletedRequestObservation,
    ScheduledRequest,
    SingleNodeSimulationPlan,
    SingleNodeSimulationResult,
)


class SimPySingleNodeEngine:
    """Run a finite deterministic trace on a FIFO resource with c channels."""

    def simulate(self, plan: SingleNodeSimulationPlan) -> SingleNodeSimulationResult:
        """Drain scheduled requests and preserve original input ordering."""
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

        environment.run()
        observations: list[CompletedRequestObservation] = [
            completed[index] for index in range(len(plan.requests))
        ]
        return SingleNodeSimulationResult(observations=observations)

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
