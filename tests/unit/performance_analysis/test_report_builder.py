"""Test performance report assembly from existing capacity calculations."""

from __future__ import annotations

import pytest

from application.performance_analysis.report_builder import (
    build_performance_analysis_report,
)
from domain.models.enums import NodeType
from domain.models.scenarios import DesignScenario, WorkloadProfile
from domain.models.topology import ArchitectureGraph
from domain.performance_analysis.report import (
    PerformanceAnalysisStatus,
    PerformanceFindingCode,
    PerformanceFindingSeverity,
)
from tests.factories import create_test_compute_node, create_test_edge, create_test_node

pytestmark = pytest.mark.unit


def _scenario(peak_rps: float = 25.0) -> DesignScenario:
    return DesignScenario(
        identifier="capacity_report",
        description="Capacity report test scenario",
        workload=WorkloadProfile(
            baseline_requests_per_second=peak_rps / 2.0,
            peak_requests_per_second=peak_rps,
        ),
    )


def _service_graph(
    service: str,
    *,
    concurrency: int = 1,
    mean_ms: float = 20.0,
) -> ArchitectureGraph:
    return ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node(
                service,
                concurrency=concurrency,
                mean_ms=mean_ms,
            ),
        ],
        edges=[create_test_edge("client", service)],
    )


def test_report_reuses_existing_capacity_calculation() -> None:
    """One slot serving in 20 ms has capacity 50 RPS; 25 RPS means 50% load."""
    graph = _service_graph("service")
    report = build_performance_analysis_report(graph, _scenario())

    client_metrics = next(
        item for item in report.nodes if item.node_identifier == "client"
    )
    service_metrics = next(
        item for item in report.nodes if item.node_identifier == "service"
    )

    assert report.scenario_identifier == "capacity_report"
    assert report.status is PerformanceAnalysisStatus.COMPLETE
    assert client_metrics.node_identifier == "client"
    assert client_metrics.incoming_requests_per_second == pytest.approx(25.0)
    assert client_metrics.estimated_capacity_requests_per_second is None
    assert client_metrics.utilization_ratio is None
    assert service_metrics.node_identifier == "service"
    assert service_metrics.incoming_requests_per_second == pytest.approx(25.0)
    assert service_metrics.estimated_capacity_requests_per_second == pytest.approx(50.0)
    assert service_metrics.utilization_ratio == pytest.approx(0.5)
    response_time = service_metrics.estimated_mean_response_time_milliseconds
    queue_wait = service_metrics.estimated_mean_queue_wait_milliseconds
    assert response_time is not None
    assert queue_wait is not None
    assert queue_wait == pytest.approx(response_time - 20.0)


@pytest.mark.parametrize(
    ("peak_rps", "expected_finding_code", "expected_utilization"),
    [
        (48.5, None, 0.97),
        (49.0, PerformanceFindingCode.CAPACITY_SATURATION, 0.98),
        (60.0, PerformanceFindingCode.CAPACITY_SATURATION, 1.2),
    ],
)
def test_saturation_finding_respects_existing_threshold(
    peak_rps: float,
    expected_finding_code: PerformanceFindingCode | None,
    expected_utilization: float,
) -> None:
    graph = _service_graph("service")
    scenario = _scenario(peak_rps)

    report = build_performance_analysis_report(graph, scenario)

    service_metrics = next(
        item for item in report.nodes if item.node_identifier == "service"
    )
    saturation_findings = [
        finding
        for finding in report.findings
        if finding.finding_code is PerformanceFindingCode.CAPACITY_SATURATION
    ]

    assert service_metrics.utilization_ratio == pytest.approx(expected_utilization)
    assert len(saturation_findings) == (0 if expected_finding_code is None else 1)
    if expected_finding_code is not None:
        finding = saturation_findings[0]
        assert finding.finding_code is expected_finding_code
        assert finding.affected_node_identifiers == ["service"]
        assert finding.severity is PerformanceFindingSeverity.ERROR


def test_unloaded_capacity_node_has_zero_utilization_not_missing_metrics() -> None:
    graph = ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node("active", concurrency=1, mean_ms=20.0),
            create_test_compute_node("idle", concurrency=2, mean_ms=20.0),
        ],
        edges=[create_test_edge("client", "active")],
    )

    report = build_performance_analysis_report(graph, _scenario())

    idle_metrics = next(item for item in report.nodes if item.node_identifier == "idle")

    assert idle_metrics.incoming_requests_per_second == pytest.approx(0.0)
    assert idle_metrics.estimated_capacity_requests_per_second == pytest.approx(100.0)
    assert idle_metrics.utilization_ratio == pytest.approx(0.0)


def test_missing_workload_does_not_turn_unknown_load_into_zero() -> None:
    graph = _service_graph("service")
    scenario = DesignScenario(
        identifier="capacity_report",
        description="No workload profile",
        workload=None,
    )

    report = build_performance_analysis_report(graph, scenario)

    service_metrics = next(
        item for item in report.nodes if item.node_identifier == "service"
    )

    assert report.status is PerformanceAnalysisStatus.UNAVAILABLE
    assert service_metrics.incoming_requests_per_second is None
    assert service_metrics.estimated_capacity_requests_per_second == pytest.approx(50.0)
    assert service_metrics.utilization_ratio is None
    assert any(
        finding.finding_code is PerformanceFindingCode.WORKLOAD_MISSING
        for finding in report.findings
    )


def test_branching_flow_limit_is_reported_without_pinning_message_text() -> None:
    graph = ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node("router"),
            create_test_compute_node("service_a"),
            create_test_compute_node("service_b"),
        ],
        edges=[
            create_test_edge("client", "router"),
            create_test_edge("router", "service_a"),
            create_test_edge("router", "service_b"),
        ],
    )

    report = build_performance_analysis_report(graph, _scenario())

    limitation = next(
        finding
        for finding in report.findings
        if finding.finding_code is PerformanceFindingCode.UNSUPPORTED_MODEL
    )

    assert limitation.severity is PerformanceFindingSeverity.WARNING
    assert limitation.affected_node_identifiers == ["router"]


def test_report_remains_valid_after_json_round_trip() -> None:
    report = build_performance_analysis_report(
        _service_graph("service"),
        _scenario(),
    )

    restored = type(report).model_validate_json(report.model_dump_json())

    assert restored == report


def test_infinite_latency_is_reported_as_unavailable_not_serialized() -> None:
    report = build_performance_analysis_report(
        _service_graph("service"),
        _scenario(peak_rps=50.0),
    )

    service_metrics = next(
        item for item in report.nodes if item.node_identifier == "service"
    )

    assert report.status is PerformanceAnalysisStatus.PARTIAL
    assert service_metrics.utilization_ratio == pytest.approx(1.0)
    assert service_metrics.estimated_mean_queue_wait_milliseconds is None
    assert service_metrics.estimated_mean_response_time_milliseconds is None
    assert any(
        finding.finding_code is PerformanceFindingCode.METRIC_UNAVAILABLE
        for finding in report.findings
    )
    assert type(report).model_validate_json(report.model_dump_json()) == report
