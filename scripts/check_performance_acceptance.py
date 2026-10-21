"""Validate persisted performance artifacts independently of LLM output."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Sequence

from pydantic import ValidationError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from domain.performance_analysis.report import (
    PerformanceAnalysisReport,
    PerformanceAnalysisStatus,
    PerformanceFindingCode,
)

_logger = logging.getLogger("performance.acceptance")


def check_artifacts(
    output_directory: Path,
    scenario_identifier: str,
    *,
    require_pdf: bool = False,
    expected_status: PerformanceAnalysisStatus | None = None,
) -> bool:
    """Validate machine-readable guarantees and optional PDF consistency."""
    json_path = output_directory / f"{scenario_identifier}_performance_analysis.json"
    pdf_path = output_directory / f"{scenario_identifier}_performance_analysis.pdf"
    try:
        report = PerformanceAnalysisReport.model_validate_json(
            json_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as exc:
        _logger.error("FAIL: invalid or missing JSON %s: %s", json_path, exc)
        return False

    failures: list[str] = []
    if report.scenario_identifier != scenario_identifier:
        failures.append("JSON scenario identifier differs from the requested file")
    if expected_status is not None and report.status is not expected_status:
        failures.append(f"Expected status {expected_status}, got {report.status}")
    identifiers = [node.node_identifier for node in report.nodes]
    if identifiers != sorted(set(identifiers)):
        failures.append("Node identifiers are duplicated or non-deterministically ordered")
    for finding in report.findings:
        affected = finding.affected_node_identifiers
        if affected != sorted(affected):
            failures.append("Affected node identifiers are not sorted")
    for identifier in identifiers:
        codes = {
            finding.finding_code
            for finding in report.findings
            if identifier in finding.affected_node_identifiers
        }
        if (
            PerformanceFindingCode.CAPACITY_SATURATION in codes
            and PerformanceFindingCode.CAPACITY_HEADROOM in codes
        ):
            failures.append(f"Contradictory capacity findings for {identifier}")

    if not pdf_path.exists():
        if require_pdf:
            failures.append(f"PDF is required but missing: {pdf_path}")
        else:
            _logger.warning("PDF absent; review StageOutcome.warnings: %s", pdf_path)
    else:
        try:
            reader = PdfReader(str(pdf_path))
            content = "\n".join(page.extract_text() or "" for page in reader.pages)
            if not reader.pages or scenario_identifier not in content:
                failures.append("PDF is empty or does not contain the scenario identifier")
        except (OSError, PdfReadError, ValueError) as exc:
            failures.append(f"PDF cannot be read: {exc}")

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
        _logger.info("PASS: artifact integrity. Stage and LLM logs need separate review.")
    return not failures


def main(argv: Sequence[str] | None = None) -> int:
    """Run artifact checks from a command line and return a process exit code."""
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
    return (
        0
        if check_artifacts(
            args.out_dir,
            args.scenario,
            require_pdf=args.require_pdf,
            expected_status=expect,
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
