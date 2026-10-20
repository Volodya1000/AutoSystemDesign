"""Regression tests for deterministic request-flow calculations.

Expected values are calculated independently from the implementation:
clients split peak load evenly, outgoing edges split load evenly, and caches
forward only their miss fraction. These tests protect existing behavior;
they do not introduce a new traffic model.
"""

from __future__ import annotations

import pytest

from domain.exceptions.model_validation_errors import ModelValidationError
from domain.models.enums import NodeType
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


def test_fan_out_splits_outgoing_rate_equally() -> None:
    """A 100 RPS source sends 50 RPS down each of its two outgoing edges."""
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

    assert incoming == {
        "client": 100.0,
        "service": 100.0,
        "database": 50.0,
        "broker": 50.0,
    }


def test_cache_forwards_only_the_miss_fraction() -> None:
    """An 80% hit rate turns 100 incoming RPS into 20 outgoing RPS."""
    graph = ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            create_test_node("cache", NodeType.CACHE),
            create_test_node("service", NodeType.COMPUTE),
        ],
        edges=[
            create_test_edge("client", "cache"),
            create_test_edge("cache", "service"),
        ],
    )

    incoming = compute_node_incoming_rps(graph, _workload())

    assert incoming["cache"] == 100.0
    assert incoming["service"] == pytest.approx(20.0)


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
