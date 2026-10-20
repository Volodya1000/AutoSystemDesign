"""Check the performance report's public data and JSON contract."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from domain.performance_analysis.report import (
    NodePerformanceMetrics,
    PerformanceAnalysisReport,
    PerformanceAnalysisStatus,
    PerformanceFinding,
    PerformanceFindingSeverity,
)

pytestmark = pytest.mark.unit


def _report() -> PerformanceAnalysisReport:
    """Build a representative report without running performance calculations."""
    return PerformanceAnalysisReport(
        scenario_identifier="online_store",
        status=PerformanceAnalysisStatus.PARTIAL,
        nodes=[
            NodePerformanceMetrics(
                node_identifier="database",
                incoming_requests_per_second=120.0,
                estimated_capacity_requests_per_second=150.0,
                utilization_ratio=0.8,
                estimated_mean_queue_wait_milliseconds=4.0,
                estimated_mean_response_time_milliseconds=24.0,
            )
        ],
        findings=[
            PerformanceFinding(
                code="capacity_headroom",
                severity=PerformanceFindingSeverity.INFO,
                title="Capacity headroom is available",
                description="The estimated load is below the estimated capacity.",
                affected_node_identifiers=["database"],
            )
        ],
        assumptions=["The values in this test are illustrative, not a model output."],
    )


def test_report_round_trips_through_json() -> None:
    report = _report()

    restored = PerformanceAnalysisReport.model_validate_json(report.model_dump_json())

    assert restored == report


def test_unavailable_metrics_are_serialized_as_null() -> None:
    report = PerformanceAnalysisReport(
        scenario_identifier="online_store",
        status=PerformanceAnalysisStatus.UNAVAILABLE,
        nodes=[NodePerformanceMetrics(node_identifier="database")],
    )

    payload: dict[str, object] = json.loads(report.model_dump_json())
    nodes = payload["nodes"]
    assert isinstance(nodes, list)
    node = nodes[0]
    assert isinstance(node, dict)
    assert node["incoming_requests_per_second"] is None
    assert node["estimated_mean_response_time_milliseconds"] is None


def test_report_collection_defaults_are_independent() -> None:
    first = PerformanceAnalysisReport(
        scenario_identifier="first",
        status=PerformanceAnalysisStatus.UNAVAILABLE,
    )
    second = PerformanceAnalysisReport(
        scenario_identifier="second",
        status=PerformanceAnalysisStatus.UNAVAILABLE,
    )

    first.assumptions.append("No workload profile was provided.")

    assert second.assumptions == []


@pytest.mark.parametrize(
    "value",
    [-1.0, float("inf")],
)
def test_incoming_rate_rejects_negative_or_non_finite_values(value: float) -> None:
    with pytest.raises(ValidationError):
        NodePerformanceMetrics(
            node_identifier="database",
            incoming_requests_per_second=value,
        )


def test_report_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        PerformanceAnalysisReport(
            scenario_identifier="online_store",
            status=PerformanceAnalysisStatus.COMPLETE,
            unexpected_field=True,
        )
