"""Regression tests for deterministic request-flow calculations.

Expected values are calculated independently from the implementation:
clients split peak load evenly, alternative edges split source traffic, fan-out
edges carry the full rate, and cache readers send only misses along the
compute-owned database fallback. These tests protect the routing contract and
its backwards-compatible default.
"""

from __future__ import annotations

import pytest

from domain.exceptions.model_validation_errors import (
    ModelValidationCode,
    ModelValidationError,
)
from domain.models.enums import EdgeRoutingMode, NodeType
from domain.models.scenarios import WorkloadProfile
from domain.models.topology import ArchitectureGraph
from domain.specifications.traffic_flow import compute_node_incoming_rps
from tests.factories import create_test_edge, create_test_node

pytestmark = pytest.mark.unit


def _workload(peak_rps: float = 100.0) -> WorkloadProfile:
    return WorkloadProfile(
        baseline_requests_per_second=peak_rps / 2.0,
        peak_requests_per_second=peak_rps,
    )


def test_linear_chain_preserves_request_rate() -> None:
    """A client and two ordinary services each receive the same 100 RPS."""
    graph = ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            create_test_node("service_a", NodeType.COMPUTE),
            create_test_node("service_b", NodeType.DATABASE),
        ],
        edges=[
            create_test_edge("client", "service_a"),
            create_test_edge("service_a", "service_b"),
        ],
    )

    assert compute_node_incoming_rps(graph, _workload()) == {
        "client": 100.0,
        "service_a": 100.0,
        "service_b": 100.0,
    }


def test_multiple_clients_split_peak_load_evenly() -> None:
    """Two clients share 100 RPS; their common downstream node receives 100."""
    graph = ArchitectureGraph(
        nodes=[
            create_test_node("client_a", NodeType.CLIENT),
            create_test_node("client_b", NodeType.CLIENT),
            create_test_node("service", NodeType.COMPUTE),
        ],
        edges=[
            create_test_edge("client_a", "service"),
            create_test_edge("client_b", "service"),
        ],
    )

    assert compute_node_incoming_rps(graph, _workload()) == {
        "client_a": 50.0,
        "client_b": 50.0,
        "service": 100.0,
    }


def test_alternative_routes_split_outgoing_rate_equally() -> None:
    """A 100 RPS source splits alternative traffic across two routes."""
    graph = ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            create_test_node("service", NodeType.COMPUTE),
            create_test_node("database", NodeType.DATABASE),
            create_test_node("broker", NodeType.MESSAGE_BROKER),
        ],
        edges=[
            create_test_edge("client", "service"),
            create_test_edge("service", "database"),
            create_test_edge("service", "broker"),
        ],
    )

    incoming = compute_node_incoming_rps(graph, _workload())

    assert incoming["database"] == pytest.approx(50.0)
    assert incoming["broker"] == pytest.approx(50.0)


def test_fan_out_sends_full_rate_to_each_dependency() -> None:
    """Each dependency called for every request receives the full source rate."""
    graph = ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            create_test_node("service", NodeType.COMPUTE),
            create_test_node("database", NodeType.DATABASE),
            create_test_node("broker", NodeType.MESSAGE_BROKER),
        ],
        edges=[
            create_test_edge("client", "service"),
            create_test_edge(
                "service", "database", routing_mode=EdgeRoutingMode.FAN_OUT
            ),
            create_test_edge("service", "broker", routing_mode=EdgeRoutingMode.FAN_OUT),
        ],
    )

    incoming = compute_node_incoming_rps(graph, _workload())

    assert incoming["database"] == pytest.approx(100.0)
    assert incoming["broker"] == pytest.approx(100.0)


def test_fan_out_dependencies_and_alternatives_can_coexist() -> None:
    """Required dependencies get full traffic while alternative routes split it."""
    graph = ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            create_test_node("service", NodeType.COMPUTE),
            create_test_node("required_db", NodeType.DATABASE),
            create_test_node("alternative_a", NodeType.COMPUTE),
            create_test_node("alternative_b", NodeType.COMPUTE),
        ],
        edges=[
            create_test_edge("client", "service"),
            create_test_edge(
                "service", "required_db", routing_mode=EdgeRoutingMode.FAN_OUT
            ),
            create_test_edge("service", "alternative_a"),
            create_test_edge("service", "alternative_b"),
        ],
    )

    incoming = compute_node_incoming_rps(graph, _workload())

    assert incoming["required_db"] == pytest.approx(100.0)
    assert incoming["alternative_a"] == pytest.approx(50.0)
    assert incoming["alternative_b"] == pytest.approx(50.0)


@pytest.mark.parametrize(
    ("hit_rate", "expected_database_rps"),
    [(0.0, 100.0), (0.8, 20.0), (1.0, 0.0)],
)
def test_cache_forwards_only_the_miss_fraction(
    hit_rate: float,
    expected_database_rps: float,
) -> None:
    """Only cache misses reach the database; cache receives every request."""
    graph = ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            create_test_node("processor", NodeType.COMPUTE),
            create_test_node(
                "cache",
                NodeType.CACHE,
                cache_hit_rate_probability=hit_rate,
            ),
            create_test_node("database", NodeType.DATABASE),
        ],
        edges=[
            create_test_edge("client", "processor"),
            create_test_edge("processor", "cache"),
            create_test_edge("processor", "database"),
        ],
    )

    incoming = compute_node_incoming_rps(graph, _workload())

    assert incoming["cache"] == pytest.approx(100.0)
    assert incoming["database"] == pytest.approx(expected_database_rps)


def test_multiple_cache_reads_from_one_compute_are_rejected() -> None:
    graph = ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            create_test_node("processor", NodeType.COMPUTE),
            create_test_node("cache_a", NodeType.CACHE),
            create_test_node("cache_b", NodeType.CACHE),
            create_test_node("database", NodeType.DATABASE),
        ],
        edges=[
            create_test_edge("client", "processor"),
            create_test_edge("processor", "cache_a"),
            create_test_edge("processor", "cache_b"),
            create_test_edge("processor", "database"),
        ],
    )

    with pytest.raises(ModelValidationError) as error:
        compute_node_incoming_rps(graph, _workload())

    assert error.value.code is ModelValidationCode.AMBIGUOUS_CACHE_MISS_PATH


def test_graph_without_clients_returns_zero_for_every_node() -> None:
    """No client means no source load; graph nodes remain in the result."""
    graph = ArchitectureGraph(
        nodes=[
            create_test_node("service_a", NodeType.COMPUTE),
            create_test_node("service_b", NodeType.DATABASE),
        ],
        edges=[create_test_edge("service_a", "service_b")],
    )

    assert compute_node_incoming_rps(graph, _workload()) == {
        "service_a": 0.0,
        "service_b": 0.0,
    }


def test_cycle_is_rejected_even_when_no_client_exists() -> None:
    """A cyclic topology is invalid independently of whether it carries load."""
    graph = ArchitectureGraph(
        nodes=[
            create_test_node("service_a", NodeType.COMPUTE),
            create_test_node("service_b", NodeType.DATABASE),
        ],
        edges=[
            create_test_edge("service_a", "service_b"),
            create_test_edge("service_b", "service_a"),
        ],
    )

    with pytest.raises(ModelValidationError):
        compute_node_incoming_rps(graph, _workload())
