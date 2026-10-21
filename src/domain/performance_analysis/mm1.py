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
    """Calculate exact steady-state M/M/1 queueing estimates.

    Kendall's A/S/c notation: the first M means Poisson arrivals
    (exponentially distributed interarrival times), the second M means
    exponentially distributed service times, and 1 means one service channel.

    Let lambda = arrival_rate_requests_per_second (requests/second) and
    mu = service_rate_requests_per_second (requests/second, ONE channel).

        rho = lambda / mu                 # utilization, dimensionless
        Wq  = lambda / [mu * (mu-lambda)] # mean queue waiting, seconds
        W   = 1 / (mu-lambda)            # mean wait + service, seconds

    The code multiplies seconds by 1000 to return milliseconds. A finite
    stationary mean exists only if lambda < mu. Otherwise the time fields
    are unavailable (None), not zero. This model assumes infinite waiting
    capacity and FIFO; it does not predict real-world p95/p99 or losses.
    See docs/performance-analysis/QUEUEING_THEORY_FOR_BEGINNERS.md.
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
