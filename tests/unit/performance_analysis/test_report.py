"""Check the public behaviour of the performance report JSON contract."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from domain.performance_analysis.report import (
    NodePerformanceMetrics,
    PerformanceAnalysisReport,
    PerformanceAnalysisStatus,
    PerformanceFinding,
    PerformanceFindingCode,
    PerformanceFindingSeverity,
)

pytestmark = pytest.mark.unit


def _report() -> PerformanceAnalysisReport:
    """Create a representative report without running performance calculations."""
    return PerformanceAnalysisReport(
        scenario_identifier="online_store",
        status=PerformanceAnalysisStatus.PARTIAL,
        estimated_longest_synchronous_path_mean_milliseconds=29.0,
        critical_path_node_identifiers=["client", "database"],
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
                finding_code=PerformanceFindingCode.CAPACITY_HEADROOM,
                severity=PerformanceFindingSeverity.INFO,
                title="Capacity headroom is available",
                description="The estimated load is below the estimated capacity.",
                affected_node_identifiers=["database"],
            )
        ],
    )


def test_report_round_trips_through_json() -> None:
    report = _report()

    restored = PerformanceAnalysisReport.model_validate_json(report.model_dump_json())

    assert restored == report


def test_unavailable_metrics_remain_null_in_json() -> None:
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
    assert payload["estimated_longest_synchronous_path_mean_milliseconds"] is None
    assert payload["critical_path_node_identifiers"] == []


def test_overload_ratio_can_exceed_one() -> None:
    node = NodePerformanceMetrics(
        node_identifier="database",
        incoming_requests_per_second=120.0,
        estimated_capacity_requests_per_second=100.0,
        utilization_ratio=1.2,
    )

    assert node.utilization_ratio == pytest.approx(1.2)


def test_finding_code_and_severity_have_stable_json_values() -> None:
    payload: dict[str, object] = json.loads(_report().model_dump_json())
    findings = payload["findings"]
    assert isinstance(findings, list)
    finding = findings[0]
    assert isinstance(finding, dict)

    assert finding["finding_code"] == "capacity_headroom"
    assert finding["severity"] == "info"


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
    payload: dict[str, object] = {
        "scenario_identifier": "online_store",
        "status": PerformanceAnalysisStatus.COMPLETE.value,
        "unexpected_field": True,
    }

    with pytest.raises(ValidationError):
        PerformanceAnalysisReport.model_validate(payload)


@pytest.mark.parametrize("invalid_value", [-1.0, float("inf"), float("nan")])
def test_longest_mean_path_rejects_invalid_estimates(invalid_value: float) -> None:
    with pytest.raises(ValidationError):
        PerformanceAnalysisReport(
            scenario_identifier="online_store",
            status=PerformanceAnalysisStatus.PARTIAL,
            estimated_longest_synchronous_path_mean_milliseconds=invalid_value,
        )


def test_old_report_json_defaults_new_optional_path_fields() -> None:
    """Adding the path estimate must not break existing stored JSON."""
    legacy_json = '{"scenario_identifier":"legacy","status":"complete"}'

    restored = PerformanceAnalysisReport.model_validate_json(legacy_json)

    assert restored.estimated_longest_synchronous_path_mean_milliseconds is None
    assert restored.critical_path_node_identifiers == []
