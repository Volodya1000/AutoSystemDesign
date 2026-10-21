"""Validate persisted performance artifacts independently of LLM output."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from domain.performance_analysis.report import (
    PerformanceAnalysisReport,
    PerformanceAnalysisStatus,
    PerformanceFindingCode,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

_logger = logging.getLogger("performance.acceptance")


def _check_report(
    report: PerformanceAnalysisReport,
    scenario_identifier: str,
    expected_status: PerformanceAnalysisStatus | None,
) -> list[str]:
    """Check guarantees that do not depend on LLM topology choices."""
    failures: list[str] = []
    if report.scenario_identifier != scenario_identifier:
        failures.append("Report identifier differs from the requested scenario")
    if expected_status is not None and report.status is not expected_status:
        failures.append(f"Expected status {expected_status}, got {report.status}")

    identifiers = [node.node_identifier for node in report.nodes]
    if identifiers != sorted(set(identifiers)):
        failures.append("Node identifiers must be unique and sorted")
    failures.extend(
        "Affected node identifiers are not sorted"
        for finding in report.findings
        if finding.affected_node_identifiers
        != sorted(finding.affected_node_identifiers)
    )
    for identifier in identifiers:
        codes = {
            finding.finding_code
            for finding in report.findings
            if identifier in finding.affected_node_identifiers
        }
        if {
            PerformanceFindingCode.CAPACITY_SATURATION,
            PerformanceFindingCode.CAPACITY_HEADROOM,
        }.issubset(codes):
            failures.append(f"Contradictory capacity findings for {identifier}")
    return failures


def _check_pdf(
    pdf_path: Path,
    scenario_identifier: str,
    *,
    require_pdf: bool,
) -> list[str]:
    """Inspect optional PDF without using it as a numeric source of truth."""
    if not pdf_path.exists():
        if require_pdf:
            return [f"Required PDF missing: {pdf_path}"]
        _logger.warning("PDF absent; inspect stage warnings: %s", pdf_path)
        return []
    try:
        reader = PdfReader(str(pdf_path))
        content = "\n".join(page.extract_text() or "" for page in reader.pages)
    except (OSError, PdfReadError, ValueError) as exc:
        return [f"PDF cannot be read: {exc}"]
    if not reader.pages or scenario_identifier not in content:
        return ["PDF is empty or missing the scenario identifier"]
    return []


def check_artifacts(
    output_directory: Path,
    scenario_identifier: str,
    *,
    require_pdf: bool = False,
    expected_status: PerformanceAnalysisStatus | None = None,
) -> bool:
    """Validate saved artifacts, leaving LLM pipeline claims for log review."""
    json_path = output_directory / f"{scenario_identifier}_performance_analysis.json"
    pdf_path = output_directory / f"{scenario_identifier}_performance_analysis.pdf"
    try:
        report = PerformanceAnalysisReport.model_validate_json(
            json_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError):
        _logger.exception("FAIL: missing or invalid JSON at %s", json_path)
        return False

    failures = _check_report(report, scenario_identifier, expected_status)
    failures.extend(_check_pdf(pdf_path, scenario_identifier, require_pdf=require_pdf))
    for failure in failures:
        _logger.error("FAIL: %s", failure)
    _logger.info(
        "Scenario=%s status=%s nodes=%d findings=%d pdf=%s",
        scenario_identifier,
        report.status.value,
        len(report.nodes),
        len(report.findings),
        pdf_path.exists(),
    )
    if not failures:
        _logger.info("PASS: artifact integrity; review stage and LLM logs separately")
    return not failures


def main(argv: Sequence[str] | None = None) -> int:
    """Run acceptance checks from a command line and return the exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--require-pdf", action="store_true")
    parser.add_argument(
        "--expect-status",
        choices=[status.value for status in PerformanceAnalysisStatus],
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    expect = (
        PerformanceAnalysisStatus(args.expect_status)
        if args.expect_status is not None
        else None
    )
    success = check_artifacts(
        args.out_dir,
        args.scenario,
        require_pdf=args.require_pdf,
        expected_status=expect,
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
