"""Contract tests for node queue metrics and synchronous path estimates."""

import pytest

from application.performance_analysis.report_builder import (
    build_performance_analysis_report,
)
from domain.models.edges import Edge
from domain.models.enums import EdgeRoutingMode, NodeType
from domain.models.nodes import ComputeNode
from domain.models.protocols import ASYNCHRONOUS_MESSAGE_QUEUE
from domain.models.scenarios import DesignScenario, WorkloadProfile
from domain.models.topology import ArchitectureGraph
from domain.performance_analysis.report import (
    PerformanceAnalysisStatus,
    PerformanceFindingCode,
)
from tests.factories import create_test_compute_node, create_test_edge, create_test_node

pytestmark = pytest.mark.unit


def _scenario() -> DesignScenario:
    return DesignScenario(
        identifier="queue_path_report",
        description="Known arrival and service rates",
        workload=WorkloadProfile(
            baseline_requests_per_second=10.0,
            peak_requests_per_second=20.0,
        ),
    )


def _service(identifier: str, mean_ms: float = 10.0) -> ComputeNode:
    return create_test_compute_node(
        identifier,
        concurrency=100,
        service_channels_per_replica=1,
        mean_ms=mean_ms,
        std_ms=mean_ms,
    )


def test_linear_chain_reports_queue_wait_and_longest_mean_path() -> None:
    graph = ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            _service("first"),
            _service("second", mean_ms=20.0),
        ],
        edges=[
            create_test_edge("client", "first"),
            create_test_edge("first", "second"),
        ],
    )

    report = build_performance_analysis_report(graph, _scenario())
    metrics = {metric.node_identifier: metric for metric in report.nodes}

    # M/M/1 equivalence: 20 RPS; service rates 100 and 50 RPS.
    assert metrics["first"].estimated_mean_queue_wait_milliseconds == pytest.approx(2.5)
    assert metrics["second"].estimated_mean_queue_wait_milliseconds == pytest.approx(
        40.0 / 3.0
    )
    assert report.estimated_longest_synchronous_path_mean_milliseconds == pytest.approx(
        12.5 + 100.0 / 3.0 + 2.0
    )
    assert report.critical_path_node_identifiers == [
        "client",
        "first",
        "second",
    ]
    assert report.status is PerformanceAnalysisStatus.COMPLETE


def test_parallel_fan_out_records_longest_path_not_sum_of_branches() -> None:
    graph = ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            _service("short"),
            _service("long", mean_ms=20.0),
        ],
        edges=[
            create_test_edge(
                "client", "short", routing_mode=EdgeRoutingMode.FAN_OUT
            ),
            create_test_edge("client", "long", routing_mode=EdgeRoutingMode.FAN_OUT),
        ],
    )

    report = build_performance_analysis_report(graph, _scenario())

    assert report.critical_path_node_identifiers == ["client", "long"]
    assert report.estimated_longest_synchronous_path_mean_milliseconds == pytest.approx(
        100.0 / 3.0 + 1.0
    )
    # It is the longest *path mean*, not E[max(T_short, T_long)].
    assert report.status is PerformanceAnalysisStatus.COMPLETE


def test_asynchronous_branch_does_not_extend_caller_path() -> None:
    graph = ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            _service("service"),
            create_test_compute_node("async_worker"),
        ],
        edges=[
            create_test_edge("client", "service"),
            Edge(
                source_identifier="service",
                target_identifier="async_worker",
                protocol=ASYNCHRONOUS_MESSAGE_QUEUE,
                network_latency_milliseconds=1.0,
            ),
        ],
    )

    report = build_performance_analysis_report(graph, _scenario())

    assert report.critical_path_node_identifiers == ["client", "service"]
    assert report.estimated_longest_synchronous_path_mean_milliseconds == pytest.approx(
        13.5
    )
    assert report.status is PerformanceAnalysisStatus.PARTIAL


def test_unknown_service_channels_keep_path_and_wait_unavailable() -> None:
    graph = ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node("service", concurrency=100),
        ],
        edges=[create_test_edge("client", "service")],
    )

    report = build_performance_analysis_report(graph, _scenario())
    service = next(item for item in report.nodes if item.node_identifier == "service")

    assert service.estimated_mean_queue_wait_milliseconds is None
    assert service.estimated_mean_response_time_milliseconds is None
    assert report.estimated_longest_synchronous_path_mean_milliseconds is None
    assert report.critical_path_node_identifiers == []
    assert report.status is PerformanceAnalysisStatus.PARTIAL
    assert PerformanceFindingCode.METRIC_UNAVAILABLE in {
        finding.finding_code for finding in report.findings
    }
