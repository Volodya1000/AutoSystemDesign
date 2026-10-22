"""Regression tests for mean-latency queueing assumptions."""

import pytest

from domain.models.edges import Edge
from domain.models.protocols import ASYNCHRONOUS_MESSAGE_QUEUE
from domain.models.topology import ArchitectureGraph
from domain.specifications.latency_validator import compute_critical_path
from tests.factories import (
    create_test_compute_node,
    create_test_latency_graph,
    create_test_latency_scenario,
)

pytestmark = pytest.mark.unit


def test_single_channel_exponential_service_matches_mm1_reference() -> None:
    graph = create_test_latency_graph(service_channels_per_replica=1)
    scenario = create_test_latency_scenario()

    result = compute_critical_path(graph, scenario)
    # Independent hand-calculated M/M/1 special case: arrival=20, service=100 RPS.
    expected_response_ms: float = 1000.0 / (100.0 - 20.0)
    expected_wait_ms: float = 20.0 * 1000.0 / (100.0 * (100.0 - 20.0))

    assert result is not None
    assert result.node_latencies_ms["service"] == pytest.approx(expected_response_ms)
    assert result.node_queue_wait_ms["service"] == pytest.approx(expected_wait_ms)
    assert result.total_latency_ms == pytest.approx(
        expected_response_ms + graph.edges[0].network_latency_milliseconds
    )


def test_unknown_channel_count_does_not_fall_back_to_maximum_concurrency() -> None:
    graph = create_test_latency_graph(concurrency=100)
    scenario = create_test_latency_scenario()

    result = compute_critical_path(graph, scenario)

    assert result is not None
    assert result.node_latencies_ms["service"] is None
    assert result.node_queue_wait_ms["service"] is None
    assert result.total_latency_ms is None


def test_zero_load_can_be_estimated_without_known_channel_count() -> None:
    baseline = create_test_latency_graph()
    # A disconnected service receives zero traffic although workload is positive.
    graph = ArchitectureGraph(nodes=baseline.nodes, edges=[])

    result = compute_critical_path(graph, create_test_latency_scenario())

    assert result is not None
    assert result.node_queue_wait_ms["service"] == pytest.approx(0.0)
    assert result.node_latencies_ms["service"] == pytest.approx(10.0)


def test_async_fire_and_forget_node_does_not_invalidate_sync_path() -> None:
    graph = create_test_latency_graph(service_channels_per_replica=1)
    async_worker = create_test_compute_node(
        "async_worker",
        concurrency=100,
        mean_ms=1000.0,
        std_ms=1000.0,
    )
    graph = ArchitectureGraph(
        nodes=[*graph.nodes, async_worker],
        edges=[
            *graph.edges,
            Edge(
                source_identifier="service",
                target_identifier="async_worker",
                protocol=ASYNCHRONOUS_MESSAGE_QUEUE,
                network_latency_milliseconds=1.0,
            ),
        ],
    )

    result = compute_critical_path(graph, create_test_latency_scenario())

    assert result is not None
    assert result.total_latency_ms is not None
    assert result.node_latencies_ms["async_worker"] is None
    service_response = result.node_latencies_ms["service"]
    assert service_response is not None
    assert result.total_latency_ms == pytest.approx(
        service_response + graph.edges[0].network_latency_milliseconds
    )
