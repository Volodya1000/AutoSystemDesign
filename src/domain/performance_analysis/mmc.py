"""Exact steady-state calculations for M/M/c queues using Erlang C."""

from math import exp, fsum, isfinite, lgamma, log, log1p

from domain.performance_analysis.queueing import (
    MAX_SUPPORTED_SERVER_COUNT,
    QueueingMetrics,
    QueueingStatus,
    create_stable_queueing_metrics,
    validate_queueing_rates,
)

MILLISECONDS_PER_SECOND = 1000.0


def compute_mmc_metrics(
    arrival_rate_requests_per_second: float,
    service_rate_requests_per_second: float,
    server_count: int,
) -> QueueingMetrics:
    """Calculate exact steady-state M/M/c means with Erlang C.

    Kendall's A/S/c notation: M means Poisson arrivals, the second M means
    exponentially distributed service times, and c is server_count:
    independently serving channels fed by ONE shared FIFO queue.

    lambda = arrival_rate_requests_per_second (requests/second)
    mu     = service_rate_requests_per_second (per-channel requests/second)
    c      = server_count (not maximum in-flight requests)
    a      = lambda / mu     # offered traffic in server equivalents
    rho    = lambda / (c*mu) # utilization per independent server

    The Erlang-C probability that an arriving request must wait is:

        term = a**c / (factorial(c) * (1-rho))
        Pwait = term / (sum(a**k / factorial(k) for k in range(c)) + term)

    Average queue waiting and response time (in seconds) are:

        Wq = Pwait / (c*mu-lambda)
        W  = Wq + 1/mu

    Multiply by 1000 for milliseconds. We use logarithms in the Erlang-C
    calculation to avoid overflow from factorials for large c. Steady-state
    values require lambda < c*mu and an unlimited FIFO waiting room.
    See docs/performance-analysis/QUEUEING_THEORY_FOR_BEGINNERS.md.
    """
    _validate_server_count(server_count)
    validate_queueing_rates(
        arrival_rate_requests_per_second,
        service_rate_requests_per_second,
    )

    total_service_rate = server_count * service_rate_requests_per_second
    if not isfinite(total_service_rate):
        message = "Total service rate is outside the finite floating-point range."
        raise ValueError(message)

    utilization_ratio = arrival_rate_requests_per_second / total_service_rate
    if not isfinite(utilization_ratio):
        message = "The utilization ratio is outside the finite floating-point range."
        raise ValueError(message)

    if arrival_rate_requests_per_second >= total_service_rate:
        return QueueingMetrics(
            status=QueueingStatus.UNSTABLE,
            utilization_ratio=utilization_ratio,
        )

    if arrival_rate_requests_per_second == 0.0:
        return QueueingMetrics(
            status=QueueingStatus.STABLE,
            utilization_ratio=0.0,
            mean_queue_wait_milliseconds=0.0,
            mean_response_time_milliseconds=(
                MILLISECONDS_PER_SECOND / service_rate_requests_per_second
            ),
        )

    offered_load = arrival_rate_requests_per_second / service_rate_requests_per_second
    probability_of_waiting = _erlang_c_probability_of_waiting(
        offered_load, utilization_ratio, server_count
    )

    remaining_service_rate = total_service_rate - arrival_rate_requests_per_second
    mean_queue_wait_milliseconds = (
        MILLISECONDS_PER_SECOND * probability_of_waiting / remaining_service_rate
    )
    mean_response_time_milliseconds = (
        mean_queue_wait_milliseconds
        + MILLISECONDS_PER_SECOND / service_rate_requests_per_second
    )
    return create_stable_queueing_metrics(
        utilization_ratio=utilization_ratio,
        mean_queue_wait_milliseconds=mean_queue_wait_milliseconds,
        mean_response_time_milliseconds=mean_response_time_milliseconds,
    )


def _validate_server_count(server_count: int) -> None:
    if (
        isinstance(server_count, bool)
        or not isinstance(server_count, int)
        or not 1 <= server_count <= MAX_SUPPORTED_SERVER_COUNT
    ):
        message = (
            "Server count must be an integer between one and "
            f"{MAX_SUPPORTED_SERVER_COUNT}."
        )
        raise ValueError(message)


def _erlang_c_probability_of_waiting(
    offered_load: float,
    utilization_ratio: float,
    server_count: int,
) -> float:
    """Compute Erlang C probability using log-scaled terms."""
    log_offered_load = log(offered_load)
    log_waiting_term = (
        server_count * log_offered_load
        - lgamma(server_count + 1)
        - log1p(-utilization_ratio)
    )
    largest_log_term = max(
        log_waiting_term,
        max(
            server_index * log_offered_load - lgamma(server_index + 1)
            for server_index in range(server_count)
        ),
    )
    scaled_no_wait_sum = fsum(
        exp(
            server_index * log_offered_load
            - lgamma(server_index + 1)
            - largest_log_term
        )
        for server_index in range(server_count)
    )
    scaled_wait_term = exp(log_waiting_term - largest_log_term)
    return scaled_wait_term / (scaled_no_wait_sum + scaled_wait_term)
