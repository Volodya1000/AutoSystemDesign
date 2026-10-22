"""Coordinate independent single-node experiments without importing SimPy."""

from application.architecture_simulation.protocols import (
    ScheduleGeneratorProtocol,
    SimulationEngineProtocol,
)
from domain.architecture_simulation.configuration import SimulationConfiguration
from domain.architecture_simulation.kernel import (
    ReplicationResult,
    SimulationWindow,
    SingleNodeSimulationPlan,
    StochasticExperimentResult,
    StochasticSingleNodePlan,
    WindowSimulationResult,
)


class StochasticExperimentRunner:
    """Execute reproducible replications without pooling request samples."""

    def __init__(
        self,
        engine: SimulationEngineProtocol,
        schedule_generator: ScheduleGeneratorProtocol,
    ) -> None:
        self._engine: SimulationEngineProtocol = engine
        self._schedule_generator: ScheduleGeneratorProtocol = schedule_generator

    def run(
        self, plan: StochasticSingleNodePlan, configuration: SimulationConfiguration
    ) -> StochasticExperimentResult:
        """Keep each independent replication available for statistical analysis."""
        window: SimulationWindow = SimulationWindow(
            warmup_seconds=configuration.warmup_seconds,
            measurement_seconds=configuration.measurement_seconds,
            max_events=configuration.max_events_per_replication,
        )
        replications: list[ReplicationResult] = []
        replication_index: int
        for replication_index in range(configuration.replications):
            arrival_seed: int = configuration.base_seed + 2 * replication_index
            service_seed: int = arrival_seed + 1
            trace: SingleNodeSimulationPlan = self._schedule_generator.generate(
                plan, window, arrival_seed, service_seed
            )
            result: WindowSimulationResult = self._engine.simulate_window(
                trace, window
            )
            replications.append(
                ReplicationResult(
                    index=replication_index,
                    arrival_seed=arrival_seed,
                    service_seed=service_seed,
                    window_result=result,
                )
            )
        return StochasticExperimentResult(replications=replications)
