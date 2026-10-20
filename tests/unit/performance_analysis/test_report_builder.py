"""Verify that the report reuses existing performance calculations."""

from __future__ import annotations

import json

import pytest

from application.performance_analysis import build_performance_report
from domain.models.enums import NodeType
from domain.models.scenarios import DesignScenario, WorkloadProfile
from domain.models.topology import ArchitectureGraph
from domain.performance_analysis.report import (
    NodePerformanceMetrics,
    PerformanceAnalysisReport,
    PerformanceAnalysisStatus,
    PerformanceFindingCode,
    PerformanceFindingSeverity,
)
from tests.factories import create_test_compute_node, create_test_edge, create_test_node

pytestmark = pytest.mark.unit


def _scenario(peak_rps: float | None = 50.0) -> DesignScenario:
    workload = (
        WorkloadProfile(
            baseline_requests_per_second=peak_rps / 2.0,
            peak_requests_per_second=peak_rps,
        )
        if peak_rps is not None
        else None
    )
    return DesignScenario(
        identifier="online_store",
        description="Test scenario",
        workload=workload,
    )


def _graph() -> ArchitectureGraph:
    return ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node(
                "api",
                concurrency=1,
                mean_ms=10.0,
                std_ms=2.0,
            ),
        ],
        edges=[create_test_edge("client", "api")],
    )


def _metrics_by_node(
    report: PerformanceAnalysisReport,
) -> dict[str, NodePerformanceMetrics]:
    """Index node metrics by identity for focused assertions."""
    return {metric.node_identifier: metric for metric in report.nodes}


def test_report_reuses_existing_load_capacity_and_latency_calculations() -> None:
    report = build_performance_report(_graph(), _scenario())
    metrics = _metrics_by_node(report)

    assert report.scenario_identifier == "online_store"
    assert report.status is PerformanceAnalysisStatus.COMPLETE
    assert metrics["client"].incoming_requests_per_second == pytest.approx(50.0)
    assert metrics["client"].estimated_capacity_requests_per_second is None

    api = metrics["api"]
    assert api.incoming_requests_per_second == pytest.approx(50.0)
    assert api.estimated_capacity_requests_per_second == pytest.approx(100.0)
    assert api.utilization_ratio == pytest.approx(0.5)

    response_time = api.estimated_mean_response_time_milliseconds
    queue_wait = api.estimated_mean_queue_wait_milliseconds
    assert response_time is not None
    assert queue_wait is not None
    assert queue_wait == pytest.approx(response_time - 10.0)

    assert any(
        finding.finding_code is PerformanceFindingCode.CAPACITY_HEADROOM
        and finding.affected_node_identifiers == ["api"]
        and finding.severity is PerformanceFindingSeverity.INFO
        for finding in report.findings
    )


def test_report_keeps_load_dependent_metrics_unavailable_without_workload() -> None:
    report = build_performance_report(_graph(), _scenario(peak_rps=None))
    metrics = _metrics_by_node(report)

    assert report.status is PerformanceAnalysisStatus.UNAVAILABLE
    assert metrics["api"].estimated_capacity_requests_per_second == pytest.approx(
        100.0
    )
    assert metrics["api"].incoming_requests_per_second is None
    assert metrics["api"].utilization_ratio is None
    assert metrics["api"].estimated_mean_queue_wait_milliseconds is None
    assert metrics["api"].estimated_mean_response_time_milliseconds is None
    assert [finding.finding_code for finding in report.findings] == [
        PerformanceFindingCode.WORKLOAD_MISSING
    ]


def test_report_flags_the_existing_capacity_saturation_threshold() -> None:
    report = build_performance_report(
        _graph(),
        _scenario(peak_rps=98.0),
    )
    metrics = _metrics_by_node(report)

    assert report.status is PerformanceAnalysisStatus.COMPLETE
    assert metrics["api"].utilization_ratio == pytest.approx(0.98)
    assert any(
        finding.finding_code is PerformanceFindingCode.CAPACITY_SATURATION
        and finding.affected_node_identifiers == ["api"]
        and finding.severity is PerformanceFindingSeverity.ERROR
        for finding in report.findings
    )


def test_infinite_latency_is_reported_as_unavailable_not_serialized() -> None:
    report = build_performance_report(_graph(), _scenario(peak_rps=100.0))
    metrics = _metrics_by_node(report)
    api = metrics["api"]

    assert report.status is PerformanceAnalysisStatus.PARTIAL
    assert api.utilization_ratio == pytest.approx(1.0)
    assert api.estimated_mean_queue_wait_milliseconds is None
    assert api.estimated_mean_response_time_milliseconds is None
    assert PerformanceFindingCode.METRIC_UNAVAILABLE in {
        finding.finding_code for finding in report.findings
    }
    assert json.loads(report.model_dump_json())["status"] == "partial"
