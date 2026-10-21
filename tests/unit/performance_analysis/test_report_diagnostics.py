"""Public behavioural tests for deterministic performance diagnostics."""

from __future__ import annotations

import pytest

from application.performance_analysis.report_builder import (
    build_performance_analysis_report,
)
from domain.models.enums import EdgeRoutingMode, NodeType
from domain.models.scenarios import DesignScenario, WorkloadProfile
from domain.models.topology import ArchitectureGraph
from domain.performance_analysis.report import (
    PerformanceAnalysisStatus,
    PerformanceFindingCode,
    PerformanceFindingSeverity,
)
from tests.factories import create_test_compute_node, create_test_edge, create_test_node

pytestmark = pytest.mark.unit


def _scenario() -> DesignScenario:
    return DesignScenario(
        identifier="diagnostic_order",
        description="Deterministic diagnostic ordering",
        workload=WorkloadProfile(
            baseline_requests_per_second=10.0,
            peak_requests_per_second=20.0,
        ),
    )


def test_permuted_graph_has_identical_report_with_tied_paths() -> None:
    """Graph input order must not affect JSON, including a tied critical path."""
    client = create_test_node("client", NodeType.CLIENT)
    alpha = create_test_compute_node(
        "alpha",
        service_channels_per_replica=1,
        mean_ms=10.0,
        std_ms=10.0,
    )
    beta = create_test_compute_node(
        "beta",
        service_channels_per_replica=1,
        mean_ms=10.0,
        std_ms=10.0,
    )
    alpha_edge = create_test_edge(
        "client", "alpha", routing_mode=EdgeRoutingMode.FAN_OUT
    )
    beta_edge = create_test_edge("client", "beta", routing_mode=EdgeRoutingMode.FAN_OUT)
    first_graph = ArchitectureGraph(
        nodes=[client, beta, alpha],
        edges=[beta_edge, alpha_edge],
    )
    second_graph = ArchitectureGraph(
        nodes=[alpha, client, beta],
        edges=[alpha_edge, beta_edge],
    )

    first = build_performance_analysis_report(first_graph, _scenario())
    second = build_performance_analysis_report(second_graph, _scenario())

    assert first.model_dump_json() == second.model_dump_json()
    assert [metric.node_identifier for metric in first.nodes] == [
        "alpha",
        "beta",
        "client",
    ]
    assert first.critical_path_node_identifiers == ["client", "alpha"]


def test_overload_findings_have_stable_severity_and_affected_nodes() -> None:
    """A saturated server must not simultaneously advertise capacity headroom."""
    graph = ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node(
                "hot",
                service_channels_per_replica=1,
                mean_ms=100.0,
                std_ms=100.0,
            ),
            create_test_compute_node(
                "cool",
                service_channels_per_replica=1,
                mean_ms=5.0,
                std_ms=5.0,
            ),
        ],
        edges=[
            create_test_edge("client", "cool", routing_mode=EdgeRoutingMode.FAN_OUT),
            create_test_edge("client", "hot", routing_mode=EdgeRoutingMode.FAN_OUT),
        ],
    )

    report = build_performance_analysis_report(graph, _scenario())
    per_node = {
        (finding.finding_code, identifier): finding
        for finding in report.findings
        for identifier in finding.affected_node_identifiers
    }

    saturation = per_node[PerformanceFindingCode.CAPACITY_SATURATION, "hot"]
    headroom = per_node[PerformanceFindingCode.CAPACITY_HEADROOM, "cool"]
    assert saturation.severity is PerformanceFindingSeverity.ERROR
    assert headroom.severity is PerformanceFindingSeverity.INFO
    assert (PerformanceFindingCode.CAPACITY_HEADROOM, "hot") not in per_node
    assert report.findings[0].finding_code is PerformanceFindingCode.CAPACITY_SATURATION
    assert report.status is PerformanceAnalysisStatus.PARTIAL


def test_multiple_cache_miss_fallbacks_report_routing_assumption() -> None:
    """Two alternative fallback DBs must not silently inherit a uniform split."""
    graph = ArchitectureGraph(
        nodes=[
            create_test_node("database_b", NodeType.DATABASE),
            create_test_node("cache", NodeType.CACHE),
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node("router"),
            create_test_node("database_a", NodeType.DATABASE),
        ],
        edges=[
            create_test_edge("client", "router"),
            create_test_edge("router", "cache"),
            create_test_edge("router", "database_b"),
            create_test_edge("router", "database_a"),
        ],
    )

    report = build_performance_analysis_report(graph, _scenario())
    routing = [
        finding
        for finding in report.findings
        if finding.finding_code is PerformanceFindingCode.UNSUPPORTED_MODEL
    ]

    assert len(routing) == 1
    assert routing[0].affected_node_identifiers == ["router"]
    assert routing[0].severity is PerformanceFindingSeverity.WARNING


def test_unknown_workload_has_stably_ordered_nodes() -> None:
    graph = ArchitectureGraph(
        nodes=[
            create_test_compute_node("zeta"),
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node("alpha"),
        ],
        edges=[],
    )
    scenario = DesignScenario(identifier="unknown_workload", description="No load")

    report = build_performance_analysis_report(graph, scenario)

    assert report.status is PerformanceAnalysisStatus.UNAVAILABLE
    assert [metric.node_identifier for metric in report.nodes] == [
        "alpha",
        "client",
        "zeta",
    ]
    assert [finding.finding_code for finding in report.findings] == [
        PerformanceFindingCode.WORKLOAD_MISSING
    ]
