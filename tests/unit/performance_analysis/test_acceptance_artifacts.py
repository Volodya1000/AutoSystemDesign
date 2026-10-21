"""Check acceptance script exit criteria on controlled JSON artifacts."""

from pathlib import Path

import pytest

from domain.performance_analysis.report import (
    NodePerformanceMetrics,
    PerformanceAnalysisReport,
    PerformanceAnalysisStatus,
    PerformanceFinding,
    PerformanceFindingCode,
    PerformanceFindingSeverity,
)
from scripts.check_performance_acceptance import check_artifacts

pytestmark = pytest.mark.unit


def _write_report(tmp_path: Path, report: PerformanceAnalysisReport) -> None:
    path = tmp_path / f"{report.scenario_identifier}_performance_analysis.json"
    path.write_text(report.model_dump_json(), encoding="utf-8")


def test_valid_partial_report_without_optional_pdf(tmp_path: Path) -> None:
    _write_report(
        tmp_path,
        PerformanceAnalysisReport(
            scenario_identifier="scenario",
            status=PerformanceAnalysisStatus.PARTIAL,
            nodes=[NodePerformanceMetrics(node_identifier="service")],
        ),
    )

    assert check_artifacts(
        tmp_path,
        "scenario",
        expected_status=PerformanceAnalysisStatus.PARTIAL,
    )


def test_required_pdf_missing_fails_even_when_json_is_valid(tmp_path: Path) -> None:
    _write_report(
        tmp_path,
        PerformanceAnalysisReport(
            scenario_identifier="scenario",
            status=PerformanceAnalysisStatus.UNAVAILABLE,
        ),
    )

    assert not check_artifacts(tmp_path, "scenario", require_pdf=True)


def test_missing_json_fails_without_guessing_results(tmp_path: Path) -> None:
    assert not check_artifacts(tmp_path, "nonexistent")


def test_capacity_findings_cannot_contradict_one_another(tmp_path: Path) -> None:
    findings = [
        PerformanceFinding(
            finding_code=code,
            severity=PerformanceFindingSeverity.WARNING,
            title="State",
            description="Machine-created test finding",
            affected_node_identifiers=["service"],
        )
        for code in (
            PerformanceFindingCode.CAPACITY_SATURATION,
            PerformanceFindingCode.CAPACITY_HEADROOM,
        )
    ]
    _write_report(
        tmp_path,
        PerformanceAnalysisReport(
            scenario_identifier="scenario",
            status=PerformanceAnalysisStatus.PARTIAL,
            nodes=[NodePerformanceMetrics(node_identifier="service")],
            findings=findings,
        ),
    )

    assert not check_artifacts(tmp_path, "scenario")


def test_wrong_expected_status_fails(tmp_path: Path) -> None:
    _write_report(
        tmp_path,
        PerformanceAnalysisReport(
            scenario_identifier="scenario",
            status=PerformanceAnalysisStatus.UNAVAILABLE,
        ),
    )

    assert not check_artifacts(
        tmp_path,
        "scenario",
        expected_status=PerformanceAnalysisStatus.COMPLETE,
    )
