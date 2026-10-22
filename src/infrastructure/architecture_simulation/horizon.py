"""Advance the discrete-event clock without draining past the measurement horizon."""

import simpy

from application.architecture_simulation.errors import SimulationEventLimitExceeded
from domain.architecture_simulation.kernel import SimulationWindow


def run_simulation_until_horizon(
    environment: simpy.Environment, window: SimulationWindow
) -> None:
    """Execute only events before the horizon and enforce the event budget."""
    event_count: int = 0
    while environment.peek() < window.horizon_seconds:
        if event_count >= window.max_events:
            raise SimulationEventLimitExceeded(
                event_limit=window.max_events,
                stopped_at_seconds=float(environment.now),
            )
        environment.step()
        event_count += 1
