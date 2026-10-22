"""Sample one virtual-time Poisson trace with reproducible independent RNGs."""

from random import Random

from application.architecture_simulation.errors import SimulationEventLimitExceeded
from domain.architecture_simulation.kernel import (
    ScheduledRequest,
    SimulationWindow,
    SingleNodeSimulationPlan,
    StochasticSingleNodePlan,
)


class PoissonGammaScheduleGenerator:
    """Generate Poisson arrivals and constant or Gamma service durations."""

    def generate(
        self,
        plan: StochasticSingleNodePlan,
        window: SimulationWindow,
        arrival_seed: int,
        service_seed: int,
    ) -> SingleNodeSimulationPlan:
        """Stop generating at the horizon or when the event budget is exhausted."""
        arrivals: Random = Random(arrival_seed)
        services: Random = Random(service_seed)
        requests: list[ScheduledRequest] = []
        arrival_seconds: float = 0.0
        if plan.arrival_rate_per_second == 0.0:
            return SingleNodeSimulationPlan(service_channels=plan.service_channels)

        while True:
            arrival_seconds += arrivals.expovariate(plan.arrival_rate_per_second)
            if arrival_seconds >= window.horizon_seconds:
                break
            if len(requests) >= window.max_events:
                raise SimulationEventLimitExceeded(
                    event_limit=window.max_events,
                    stopped_at_seconds=arrival_seconds,
                )
            service_seconds: float = self._sample_service(plan, services)
            requests.append(
                ScheduledRequest(
                    arrival_seconds=arrival_seconds,
                    service_seconds=service_seconds,
                )
            )
        return SingleNodeSimulationPlan(
            service_channels=plan.service_channels, requests=requests
        )

    @staticmethod
    def _sample_service(
        plan: StochasticSingleNodePlan, random_generator: Random
    ) -> float:
        """Match the specified mean and standard deviation with a Gamma law."""
        if plan.std_service_seconds == 0.0:
            return plan.mean_service_seconds
        shape: float = (plan.mean_service_seconds / plan.std_service_seconds) ** 2
        scale: float = plan.std_service_seconds**2 / plan.mean_service_seconds
        service_seconds: float = random_generator.gammavariate(shape, scale)
        if service_seconds <= 0.0:
            message: str = "Gamma sampling produced a nonpositive duration"
            raise ValueError(message)
        return service_seconds
