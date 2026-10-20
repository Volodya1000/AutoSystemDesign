"""Regression tests for mean latency and percentile-SLO semantics."""

from __future__ import annotations

import pytest

from application.performance_analysis.report_builder import (
    build_performance_analysis_report,
)
from domain.models.enums import NodeType
from domain.models.requirements import LatencyRequirement
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
        identifier="latency_slo_test",
        description="A percentile target that the current model cannot evaluate",
        workload=WorkloadProfile(
            baseline_requests_per_second=10.0,
            peak_requests_per_second=20.0,
        ),
        requirements=[LatencyRequirement(threshold_value=1.0, percentile=99.0)],
    )


def _graph() -> ArchitectureGraph:
    return ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node(
                "service",
                concurrency=1,
                mean_ms=10.0,
                std_ms=10.0,
            ),
        ],
        edges=[create_test_edge("client", "service")],
    )


def test_percentile_target_is_not_evaluated_and_mean_remains_available() -> None:
    report = build_performance_analysis_report(_graph(), _scenario())

    service_metrics = next(
        metrics for metrics in report.nodes if metrics.node_identifier == "service"
    )
    findings = [
        finding
        for finding in report.findings
        if finding.finding_code is PerformanceFindingCode.LATENCY_NOT_EVALUATED
    ]

    assert report.status is PerformanceAnalysisStatus.PARTIAL
    assert service_metrics.estimated_mean_response_time_milliseconds is not None
    assert service_metrics.estimated_mean_response_time_milliseconds > 1.0
    assert len(findings) == 1
    assert findings[0].affected_node_identifiers
