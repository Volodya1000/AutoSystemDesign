"""Check the observable scheduling rules of the real SimPy adapter.

All expected numbers follow from fixed, hand-computable event traces.
Tests assert outcomes, not implementation strings or SimPy internals.
"""

import pytest
from pydantic import ValidationError

from application.architecture_simulation.protocols import SimulationEngineProtocol
from domain.architecture_simulation.kernel import (
    CompletedRequestObservation,
    ScheduledRequest,
    SingleNodeSimulationPlan,
    SingleNodeSimulationResult,
)
from infrastructure.architecture_simulation.simpy_engine import SimPySingleNodeEngine

pytestmark = pytest.mark.unit


def _run(
    requests: list[tuple[float, float]], channels: int = 1
) -> SingleNodeSimulationResult:
    engine: SimulationEngineProtocol = SimPySingleNodeEngine()
    return engine.simulate(
        SingleNodeSimulationPlan(
            service_channels=channels,
            requests=[
                ScheduledRequest(arrival_seconds=arrival, service_seconds=service)
                for arrival, service in requests
            ],
        )
    )


def test_one_channel_serves_simultaneous_requests_in_input_order() -> None:
    result = _run([(0, 2), (0, 1), (0, 1)])

    assert [item.service_start_seconds for item in result.observations] == [
        0.0,
        2.0,
        3.0,
    ]
    assert [item.completion_seconds for item in result.observations] == [
        2.0,
        3.0,
        4.0,
    ]
    assert [item.wait_seconds for item in result.observations] == [0.0, 2.0, 3.0]
    assert [item.response_seconds for item in result.observations] == [
        2.0,
        3.0,
        4.0,
    ]


def test_two_channels_start_two_simultaneous_requests_without_waiting() -> None:
    result = _run([(0, 2), (0, 2), (0, 1)], channels=2)

    assert [item.service_start_seconds for item in result.observations] == [
        0.0,
        0.0,
        2.0,
    ]
    assert [item.completion_seconds for item in result.observations] == [
        2.0,
        2.0,
        3.0,
    ]


def test_later_idle_arrival_does_not_incur_queue_time() -> None:
    result = _run([(0, 1), (3, 1)])

    assert [item.wait_seconds for item in result.observations] == [0.0, 0.0]
    assert [item.response_seconds for item in result.observations] == [1.0, 1.0]


def test_out_of_order_schedule_returns_observations_in_original_order() -> None:
    result = _run([(3, 1), (0, 2)])

    assert [item.request_index for item in result.observations] == [0, 1]
    assert [item.arrival_seconds for item in result.observations] == [3.0, 0.0]
    assert [item.completion_seconds for item in result.observations] == [4.0, 2.0]


def test_empty_schedule_has_no_observations() -> None:
    assert _run([]).observations == []


def test_each_run_is_independent_of_the_previous_run() -> None:
    engine = SimPySingleNodeEngine()
    plan = SingleNodeSimulationPlan(
        service_channels=1,
        requests=[
            ScheduledRequest(arrival_seconds=0, service_seconds=1),
            ScheduledRequest(arrival_seconds=0, service_seconds=1),
        ],
    )

    first = engine.simulate(plan)
    engine.simulate(SingleNodeSimulationPlan(service_channels=2))
    second = engine.simulate(plan)

    assert first == second
    assert [item.completion_seconds for item in second.observations] == [1.0, 2.0]


def test_scheduled_requests_can_round_trip_through_json() -> None:
    plan = SingleNodeSimulationPlan(
        service_channels=2,
        requests=[ScheduledRequest(arrival_seconds=1.5, service_seconds=2.5)],
    )

    restored = SingleNodeSimulationPlan.model_validate_json(plan.model_dump_json())

    assert restored == plan


@pytest.mark.parametrize("invalid", [0.0, -1.0, float("inf"), float("nan")])
def test_invalid_service_durations_are_rejected(invalid: float) -> None:
    with pytest.raises(ValidationError):
        ScheduledRequest(arrival_seconds=0, service_seconds=invalid)


def test_zero_channels_are_rejected() -> None:
    with pytest.raises(ValidationError):
        SingleNodeSimulationPlan(service_channels=0)


def test_time_travel_in_observations_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CompletedRequestObservation(
            request_index=0,
            arrival_seconds=2,
            service_start_seconds=1,
            completion_seconds=3,
        )


def test_observation_round_trip_preserves_elapsed_times() -> None:
    result = _run([(0, 2), (0, 1)])

    restored = SingleNodeSimulationResult.model_validate_json(
        result.model_dump_json()
    )

    assert restored == result
    assert restored.observations[1].wait_seconds == 2.0
