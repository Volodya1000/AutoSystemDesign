"""Test stochastic reproducibility, cohort censoring and bounded execution."""

import pytest
from pydantic import ValidationError

from application.architecture_simulation.errors import SimulationEventLimitExceeded
from application.architecture_simulation.experiments import StochasticExperimentRunner
from domain.architecture_simulation.configuration import SimulationConfiguration
from domain.architecture_simulation.kernel import (
    ScheduledRequest,
    SimulationWindow,
    SingleNodeSimulationPlan,
    StochasticExperimentResult,
    StochasticSingleNodePlan,
    WindowSimulationResult,
)
from infrastructure.architecture_simulation.simpy_engine import SimPySingleNodeEngine
from infrastructure.architecture_simulation.stochastic_schedule import (
    PoissonGammaScheduleGenerator,
)

pytestmark = pytest.mark.unit


def _run(
    plan: StochasticSingleNodePlan, configuration: SimulationConfiguration
) -> StochasticExperimentResult:
    runner: StochasticExperimentRunner = StochasticExperimentRunner(
        engine=SimPySingleNodeEngine(),
        schedule_generator=PoissonGammaScheduleGenerator(),
    )
    return runner.run(plan, configuration)


def test_horizon_censors_unfinished_requests_without_draining() -> None:
    engine: SimPySingleNodeEngine = SimPySingleNodeEngine()
    result: WindowSimulationResult = engine.simulate_window(
        SingleNodeSimulationPlan(
            service_channels=1,
            requests=[
                ScheduledRequest(arrival_seconds=0, service_seconds=2),
                ScheduledRequest(arrival_seconds=1, service_seconds=1),
                ScheduledRequest(arrival_seconds=2, service_seconds=1),
                ScheduledRequest(arrival_seconds=3.5, service_seconds=2),
            ],
        ),
        SimulationWindow(
            warmup_seconds=1,
            measurement_seconds=3,
            max_events=100,
        ),
    )

    assert result.warmup_arrivals == 1
    assert result.measured_arrivals == 3
    assert result.unfinished == 2
    assert len(result.observations) == 1
    assert result.observations[0].completion_seconds == 3


def test_seeded_replications_are_reproducible_and_separately_identified() -> None:
    plan: StochasticSingleNodePlan = StochasticSingleNodePlan(
        service_channels=2,
        arrival_rate_per_second=8,
        mean_service_seconds=0.1,
        std_service_seconds=0.1,
    )
    settings: SimulationConfiguration = SimulationConfiguration(
        warmup_seconds=2,
        measurement_seconds=4,
        replications=3,
        base_seed=101,
        max_events_per_replication=10_000,
    )
    result: StochasticExperimentResult = _run(plan, settings)

    assert result == _run(plan, settings)
    assert len(result.replications) == 3
    assert len({item.arrival_seed for item in result.replications}) == 3
    assert result.replications[0].window_result != result.replications[1].window_result
    assert all(
        item.window_result.measured_arrivals
        == len(item.window_result.observations) + item.window_result.unfinished
        for item in result.replications
    )


def test_zero_arrival_rate_produces_no_requests() -> None:
    result: StochasticExperimentResult = _run(
        StochasticSingleNodePlan(
            service_channels=1,
            arrival_rate_per_second=0,
            mean_service_seconds=0.1,
            std_service_seconds=0,
        ),
        SimulationConfiguration(
            warmup_seconds=0,
            measurement_seconds=10,
            replications=2,
        ),
    )

    assert all(
        replication.window_result.measured_arrivals == 0
        for replication in result.replications
    )
    assert all(
        replication.window_result.unfinished == 0 for replication in result.replications
    )


def test_constant_service_is_unaffected_by_other_service_seeds() -> None:
    generator: PoissonGammaScheduleGenerator = PoissonGammaScheduleGenerator()
    plan: StochasticSingleNodePlan = StochasticSingleNodePlan(
        service_channels=2,
        arrival_rate_per_second=10,
        mean_service_seconds=0.5,
        std_service_seconds=0,
    )
    window: SimulationWindow = SimulationWindow(
        warmup_seconds=0,
        measurement_seconds=5,
        max_events=1000,
    )
    first: SingleNodeSimulationPlan = generator.generate(plan, window, 11, 22)
    second: SingleNodeSimulationPlan = generator.generate(plan, window, 11, 33)

    assert first == second
    assert first.requests
    assert all(request.service_seconds == 0.5 for request in first.requests)


def test_gamma_service_rng_does_not_shift_arrival_times() -> None:
    generator: PoissonGammaScheduleGenerator = PoissonGammaScheduleGenerator()
    plan: StochasticSingleNodePlan = StochasticSingleNodePlan(
        service_channels=1,
        arrival_rate_per_second=10,
        mean_service_seconds=0.5,
        std_service_seconds=0.5,
    )
    window: SimulationWindow = SimulationWindow(
        warmup_seconds=0,
        measurement_seconds=5,
        max_events=1000,
    )
    first: SingleNodeSimulationPlan = generator.generate(plan, window, 11, 22)
    second: SingleNodeSimulationPlan = generator.generate(plan, window, 11, 33)

    assert [r.arrival_seconds for r in first.requests] == [
        r.arrival_seconds for r in second.requests
    ]
    assert [r.service_seconds for r in first.requests] != [
        r.service_seconds for r in second.requests
    ]
    assert all(r.service_seconds > 0 for r in first.requests)


def test_event_budget_failure_is_not_a_successful_replication() -> None:
    engine: SimPySingleNodeEngine = SimPySingleNodeEngine()
    with pytest.raises(SimulationEventLimitExceeded):
        engine.simulate_window(
            SingleNodeSimulationPlan(
                service_channels=1,
                requests=[ScheduledRequest(arrival_seconds=0, service_seconds=1)],
            ),
            SimulationWindow(warmup_seconds=0, measurement_seconds=5, max_events=1),
        )


def test_generation_event_budget_fails_before_allocating_large_trace() -> None:
    generator: PoissonGammaScheduleGenerator = PoissonGammaScheduleGenerator()
    with pytest.raises(SimulationEventLimitExceeded):
        generator.generate(
            StochasticSingleNodePlan(
                service_channels=1,
                arrival_rate_per_second=1000,
                mean_service_seconds=0.1,
                std_service_seconds=0,
            ),
            SimulationWindow(warmup_seconds=0, measurement_seconds=10, max_events=2),
            7,
            8,
        )


def test_measured_cohort_accounting_rejects_lost_requests() -> None:
    with pytest.raises(ValidationError):
        WindowSimulationResult(measured_arrivals=2, unfinished=0, warmup_arrivals=0)


def test_invalid_service_moments_are_rejected() -> None:
    with pytest.raises(ValidationError):
        StochasticSingleNodePlan(
            service_channels=1,
            arrival_rate_per_second=10,
            mean_service_seconds=0,
            std_service_seconds=1,
        )


def test_stochastic_experiment_json_round_trip() -> None:
    experiment: StochasticExperimentResult = _run(
        StochasticSingleNodePlan(
            service_channels=2,
            arrival_rate_per_second=3,
            mean_service_seconds=0.1,
            std_service_seconds=0,
        ),
        SimulationConfiguration(
            warmup_seconds=1,
            measurement_seconds=3,
            replications=1,
            base_seed=55,
        ),
    )

    assert experiment == StochasticExperimentResult.model_validate_json(
        experiment.model_dump_json()
    )
