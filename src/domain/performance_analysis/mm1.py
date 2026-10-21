"""Exact steady-state calculations for an M/M/1 queue."""

from math import isfinite

from domain.performance_analysis.queueing import (
    QueueingMetrics,
    QueueingStatus,
    create_stable_queueing_metrics,
    validate_queueing_rates,
)

MILLISECONDS_PER_SECOND = 1000.0


def compute_mm1_metrics(
    arrival_rate_requests_per_second: float,
    service_rate_requests_per_second: float,
) -> QueueingMetrics:
    """Calculate M/M/1 mean queue wait and response time.

    Rates are measured in requests per second. The model assumes a Poisson
    arrival process, exponentially distributed service times, one independent
    server, and an unbounded queue in steady state.
    """
    validate_queueing_rates(
        arrival_rate_requests_per_second,
        service_rate_requests_per_second,
    )

    utilization_ratio = (
        arrival_rate_requests_per_second / service_rate_requests_per_second
    )
    if not isfinite(utilization_ratio):
        message = "The utilization ratio is outside the finite floating-point range."
        raise ValueError(message)

    if arrival_rate_requests_per_second >= service_rate_requests_per_second:
        return QueueingMetrics(
            status=QueueingStatus.UNSTABLE,
            utilization_ratio=utilization_ratio,
        )

    rate_difference = (
        service_rate_requests_per_second - arrival_rate_requests_per_second
    )
    mean_queue_wait_milliseconds = (
        MILLISECONDS_PER_SECOND * utilization_ratio / rate_difference
    )
    mean_response_time_milliseconds = MILLISECONDS_PER_SECOND / rate_difference
    return create_stable_queueing_metrics(
        utilization_ratio=utilization_ratio,
        mean_queue_wait_milliseconds=mean_queue_wait_milliseconds,
        mean_response_time_milliseconds=mean_response_time_milliseconds,
    )
