"""Finite-queue tests: unsupported blocking must not become invented metrics."""

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


def _scenario() -> DesignScenario:
    return DesignScenario(
        identifier="bounded_queue",
        description="Finite buffer acceptance",
        workload=WorkloadProfile(
            baseline_requests_per_second=10.0,
            peak_requests_per_second=20.0,
        ),
    )


@pytest.mark.parametrize(
    ("queue_size", "expected_wait"),
    [
        (0, None),
        (5, 2.5),
    ],
)
def test_active_finite_queue_has_explicit_diagnostic(
    queue_size: int,
    expected_wait: float | None,
) -> None:
    graph = ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node(
                "service",
                concurrency=100,
                service_channels_per_replica=1,
                queue_size=queue_size,
                mean_ms=10.0,
                std_ms=10.0,
            ),
        ],
        edges=[create_test_edge("client", "service")],
    )

    report = build_performance_analysis_report(graph, _scenario())
    service = next(item for item in report.nodes if item.node_identifier == "service")
    findings = [
        finding
        for finding in report.findings
        if finding.finding_code is PerformanceFindingCode.BOUNDED_QUEUE_UNMODELED
    ]

    assert len(findings) == 1
    assert findings[0].severity is PerformanceFindingSeverity.WARNING
    assert findings[0].affected_node_identifiers == ["service"]
    assert report.status is PerformanceAnalysisStatus.PARTIAL
    if expected_wait is None:
        assert service.estimated_mean_queue_wait_milliseconds is None
        assert service.estimated_mean_response_time_milliseconds is None
        assert report.estimated_longest_synchronous_path_mean_milliseconds is None
    else:
        # Explicit infinite-waiting-room proxy, NOT a finite-buffer prediction.
        assert service.estimated_mean_queue_wait_milliseconds == pytest.approx(
            expected_wait
        )
        assert service.estimated_mean_response_time_milliseconds == pytest.approx(
            expected_wait + 10.0
        )


def test_disconnected_zero_buffer_has_no_false_warning() -> None:
    graph = ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node(
                "active",
                queue_size=5,
                service_channels_per_replica=1,
            ),
            create_test_compute_node(
                "idle",
                queue_size=0,
                service_channels_per_replica=1,
            ),
        ],
        edges=[create_test_edge("client", "active")],
    )

    report = build_performance_analysis_report(graph, _scenario())
    idle = next(item for item in report.nodes if item.node_identifier == "idle")
    bounded_findings = [
        finding
        for finding in report.findings
        if finding.finding_code is PerformanceFindingCode.BOUNDED_QUEUE_UNMODELED
    ]

    assert idle.incoming_requests_per_second == pytest.approx(0.0)
    assert idle.estimated_mean_queue_wait_milliseconds == pytest.approx(0.0)
    assert bounded_findings[0].affected_node_identifiers == ["active"]
    assert len(bounded_findings) == 1
