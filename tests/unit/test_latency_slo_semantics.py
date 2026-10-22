"""Regression tests for mean latency and percentile-SLO semantics."""

from __future__ import annotations

import pytest

from application.performance_analysis.report_builder import (
    build_performance_analysis_report,
)
from domain.performance_analysis.report import PerformanceAnalysisStatus
from tests.factories import create_test_latency_graph, create_test_latency_scenario

pytestmark = pytest.mark.unit


def test_percentile_target_is_not_evaluated_and_mean_remains_available() -> None:
    report = build_performance_analysis_report(
        create_test_latency_graph(service_channels_per_replica=1),
        create_test_latency_scenario(),
    )

    service_metrics = next(
        metrics for metrics in report.nodes if metrics.node_identifier == "service"
    )
    assert report.findings == []
    assert report.status is PerformanceAnalysisStatus.PARTIAL
    assert service_metrics.estimated_mean_response_time_milliseconds is not None
    assert service_metrics.estimated_mean_response_time_milliseconds > 1.0
    assert report.estimated_longest_synchronous_path_mean_milliseconds is not None
