"""Numerical, stability, and domain-semantics tests for M/M/c."""

import math

import pytest
from pydantic import ValidationError

from domain.models.nodes import ComputeNode
from domain.performance_analysis.mm1 import compute_mm1_metrics
from domain.performance_analysis.mmc import compute_mmc_metrics
from domain.performance_analysis.queueing import QueueingStatus
from tests.factories import create_test_compute_node
from tests.unit.performance_analysis.assertions import assert_unstable_queueing_metrics

pytestmark = pytest.mark.unit


def test_single_server_matches_mm1_reference() -> None:
    mm1_result = compute_mm1_metrics(10.0, 20.0)
    mmc_result = compute_mmc_metrics(10.0, 20.0, server_count=1)

    assert mmc_result.status is mm1_result.status
    assert mmc_result.utilization_ratio == pytest.approx(
        mm1_result.utilization_ratio
    )
    assert mmc_result.mean_queue_wait_milliseconds == pytest.approx(
        mm1_result.mean_queue_wait_milliseconds
    )
    assert mmc_result.mean_response_time_milliseconds == pytest.approx(
        mm1_result.mean_response_time_milliseconds
    )


def test_erlang_c_example_matches_hand_calculation() -> None:
    result = compute_mmc_metrics(10.0, 20.0, server_count=2)

    assert result.status is QueueingStatus.STABLE
    assert result.utilization_ratio == pytest.approx(0.25)
    assert result.mean_queue_wait_milliseconds == pytest.approx(10.0 / 3.0)
    assert result.mean_response_time_milliseconds == pytest.approx(160.0 / 3.0)


def test_more_servers_reduce_waiting_for_the_same_load() -> None:
    two_servers = compute_mmc_metrics(10.0, 20.0, server_count=2)
    three_servers = compute_mmc_metrics(10.0, 20.0, server_count=3)

    assert (
        three_servers.mean_queue_wait_milliseconds
        < two_servers.mean_queue_wait_milliseconds
    )


def test_waiting_grows_as_the_system_approaches_capacity() -> None:
    lower_load = compute_mmc_metrics(20.0, 20.0, server_count=2)
    near_capacity = compute_mmc_metrics(39.9, 20.0, server_count=2)

    assert (
        near_capacity.mean_queue_wait_milliseconds
        > lower_load.mean_queue_wait_milliseconds
    )


def test_unstable_multiserver_queue_has_no_finite_steady_state_times() -> None:
    result = compute_mmc_metrics(45.0, 20.0, server_count=2)

    assert result.utilization_ratio == pytest.approx(1.125)
    assert_unstable_queueing_metrics(result)


def test_erlang_c_remains_numerically_stable_for_many_servers() -> None:
    result = compute_mmc_metrics(19_900.0, 20.0, server_count=1_000)

    assert result.status is QueueingStatus.STABLE
    assert math.isfinite(result.mean_queue_wait_milliseconds)
    assert math.isfinite(result.mean_response_time_milliseconds)


@pytest.mark.parametrize("server_count", [0, -1, 10_001])
def test_unsupported_server_counts_are_rejected(server_count: int) -> None:
    with pytest.raises(ValueError, match=r".+"):
        compute_mmc_metrics(10.0, 20.0, server_count)


def test_queueing_servers_are_not_inferred_from_maximum_concurrency() -> None:
    node = create_test_compute_node("service", concurrency=100)

    assert node.queueing_server_count is None

    payload = node.model_dump()
    payload["replicas_count"] = 3
    payload["service_channels_per_replica"] = 2
    configured_node = ComputeNode.model_validate(payload)

    assert configured_node.queueing_server_count == 6

    payload["service_channels_per_replica"] = 0
    with pytest.raises(ValidationError):
        ComputeNode.model_validate(payload)
