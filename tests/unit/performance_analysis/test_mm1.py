"""Numerical and boundary tests for the M/M/1 queue model."""

import json

import pytest
from pydantic import ValidationError

from domain.performance_analysis.mm1 import compute_mm1_metrics
from domain.performance_analysis.queueing import QueueingMetrics, QueueingStatus

pytestmark = pytest.mark.unit


def test_mm1_matches_hand_calculated_example() -> None:
    result = compute_mm1_metrics(
        arrival_rate_requests_per_second=10.0,
        service_rate_requests_per_second=20.0,
    )

    assert result.status is QueueingStatus.STABLE
    assert result.utilization_ratio == pytest.approx(0.5)
    assert result.mean_queue_wait_milliseconds == pytest.approx(50.0)
    assert result.mean_response_time_milliseconds == pytest.approx(100.0)


def test_zero_arrival_rate_has_no_queue_wait_but_service_time_remains() -> None:
    result = compute_mm1_metrics(
        arrival_rate_requests_per_second=0.0,
        service_rate_requests_per_second=20.0,
    )

    assert result.status is QueueingStatus.STABLE
    assert result.utilization_ratio == pytest.approx(0.0)
    assert result.mean_queue_wait_milliseconds == pytest.approx(0.0)
    assert result.mean_response_time_milliseconds == pytest.approx(50.0)


def test_queue_near_stability_has_large_finite_estimates() -> None:
    result = compute_mm1_metrics(
        arrival_rate_requests_per_second=19.999,
        service_rate_requests_per_second=20.0,
    )

    assert result.status is QueueingStatus.STABLE
    assert result.utilization_ratio == pytest.approx(0.99995)
    assert result.mean_queue_wait_milliseconds == pytest.approx(999_950.0)
    assert result.mean_response_time_milliseconds == pytest.approx(1_000_000.0)


@pytest.mark.parametrize(
    ("arrival_rate", "expected_utilization"),
    [(20.0, 1.0), (30.0, 1.5)],
)
def test_unstable_queue_has_no_finite_steady_state_times(
    arrival_rate: float,
    expected_utilization: float,
) -> None:
    result = compute_mm1_metrics(
        arrival_rate_requests_per_second=arrival_rate,
        service_rate_requests_per_second=20.0,
    )

    assert result.status is QueueingStatus.UNSTABLE
    assert result.utilization_ratio == pytest.approx(expected_utilization)
    assert result.mean_queue_wait_milliseconds is None
    assert result.mean_response_time_milliseconds is None

    serialized = json.loads(result.model_dump_json())
    assert serialized["mean_queue_wait_milliseconds"] is None
    assert serialized["mean_response_time_milliseconds"] is None


@pytest.mark.parametrize(
    ("arrival_rate", "service_rate"),
    [
        (-1.0, 20.0),
        (float("nan"), 20.0),
        (float("inf"), 20.0),
        (10.0, 0.0),
        (10.0, -1.0),
        (10.0, float("nan")),
        (10.0, float("inf")),
    ],
)
def test_invalid_rates_are_rejected(
    arrival_rate: float,
    service_rate: float,
) -> None:
    with pytest.raises(ValueError):
        compute_mm1_metrics(arrival_rate, service_rate)


def test_result_contract_rejects_inconsistent_stability_state() -> None:
    with pytest.raises(ValidationError):
        QueueingMetrics(
            status=QueueingStatus.STABLE,
            utilization_ratio=1.0,
            mean_queue_wait_milliseconds=0.0,
            mean_response_time_milliseconds=50.0,
        )
