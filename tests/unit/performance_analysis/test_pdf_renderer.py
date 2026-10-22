"""PDF presentation tests using real Cyrillic font embedding and text extraction."""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING

import pytest
from pypdf import PdfReader

if TYPE_CHECKING:
    from pathlib import Path

from domain.performance_analysis.report import (
    NodePerformanceMetrics,
    PerformanceAnalysisReport,
    PerformanceAnalysisStatus,
    PerformanceFinding,
    PerformanceFindingCode,
    PerformanceFindingSeverity,
)
from infrastructure.performance_analysis.pdf_renderer import (
    PdfFontUnavailableError,
    PerformanceReportPdfRenderer,
)

pytestmark = pytest.mark.unit


def _report(node_count: int = 1) -> PerformanceAnalysisReport:
    return PerformanceAnalysisReport(
        scenario_identifier="load_test_пример",
        status=PerformanceAnalysisStatus.PARTIAL,
        nodes=[
            NodePerformanceMetrics(
                node_identifier=f"api_{index}_" + "длинный_идентификатор_" * 7,
                incoming_requests_per_second=float(index),
                estimated_capacity_requests_per_second=100.0,
                utilization_ratio=float(index) / 100.0,
                estimated_mean_queue_wait_milliseconds=None,
                estimated_mean_response_time_milliseconds=10.0,
            )
            for index in range(node_count)
        ],
        findings=[
            PerformanceFinding(
                finding_code=PerformanceFindingCode.BOUNDED_QUEUE_UNMODELED,
                severity=PerformanceFindingSeverity.WARNING,
                title="Ограниченная очередь",
                description="При превышении буфера часть оценок недоступна.",
                affected_node_identifiers=["api_0"],
                recommendation="Проверьте политику отказов и входящий поток.",
            )
        ],
        critical_path_node_identifiers=["client", "api_0"],
        estimated_longest_synchronous_path_mean_milliseconds=15.0,
    )


def test_pdf_shows_calculated_metrics_without_unassessed_warnings() -> None:
    pdf_bytes = PerformanceReportPdfRenderer().render(_report())
    reader = PdfReader(BytesIO(pdf_bytes))
    text = "\n".join(page.extract_text() for page in reader.pages)

    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 2000
    assert "Анализ производительности" in text
    assert "load_test_пример" in text
    assert "15.00 мс" in text
    assert "Ограниченная очередь" not in text
    assert "часть характеристик" not in text
    assert "нет оценки" not in text


def test_long_identifiers_and_many_rows_paginate() -> None:
    pdf_bytes = PerformanceReportPdfRenderer().render(_report(node_count=90))
    reader = PdfReader(BytesIO(pdf_bytes))
    text = "\n".join(page.extract_text() for page in reader.pages)

    assert len(reader.pages) > 1
    assert "api_89" in text
    assert "Выявленные риски перегрузки" not in text


def test_missing_font_reports_explicit_optional_failure(tmp_path: Path) -> None:
    renderer = PerformanceReportPdfRenderer(font_path=tmp_path / "absent.ttf")

    with pytest.raises(PdfFontUnavailableError, match="Unicode TrueType font"):
        renderer.render(_report())


def test_unavailable_report_does_not_invent_metrics() -> None:
    report = PerformanceAnalysisReport(
        scenario_identifier="no_workload",
        status=PerformanceAnalysisStatus.UNAVAILABLE,
    )
    reader = PdfReader(BytesIO(PerformanceReportPdfRenderer().render(report)))
    text = "\n".join(page.extract_text() for page in reader.pages)

    assert "no_workload" in text
    assert "Недоступен" not in text
    assert "часть характеристик" not in text
    assert "Выявленные риски перегрузки" not in text


def test_pdf_omits_unassessed_diagnostics_while_preserving_json() -> None:
    """PDF excludes unsupported calculations without mutating structured findings."""
    report = _report()
    pdf_bytes = PerformanceReportPdfRenderer().render(report)
    text = "\n".join(
        page.extract_text() for page in PdfReader(BytesIO(pdf_bytes)).pages
    )

    assert "[warning]" not in text
    assert "bounded_queue_unmodeled" not in text
    assert (
        report.findings[0].finding_code
        is PerformanceFindingCode.BOUNDED_QUEUE_UNMODELED
    )
    assert report.findings[0].title not in text



def test_pdf_is_unchanged_when_legacy_nonactionable_findings_are_removed() -> None:
    """Removing obsolete JSON diagnostics must not change the readable PDF."""
    report = _report()
    without_obsolete_findings = report.model_copy(update={"findings": []})

    old_reader = PdfReader(BytesIO(PerformanceReportPdfRenderer().render(report)))
    new_reader = PdfReader(
        BytesIO(PerformanceReportPdfRenderer().render(without_obsolete_findings))
    )
    old_pages = [page.extract_text() for page in old_reader.pages]
    new_pages = [page.extract_text() for page in new_reader.pages]

    assert old_pages == new_pages


def test_pdf_keeps_request_source_outside_processing_table() -> None:
    """The client is part of the route but cannot have processing capacity."""
    report = _report()
    report.nodes.append(
        NodePerformanceMetrics(
            node_identifier="client",
            incoming_requests_per_second=60.0,
        )
    )
    text = "\n".join(
        page.extract_text()
        for page in PdfReader(
            BytesIO(PerformanceReportPdfRenderer().render(report))
        ).pages
    )
    assert text.count("client") == 1
    assert "Критический путь: client" in text


def test_repeated_headroom_diagnostics_are_not_echoed_in_pdf() -> None:
    """Calculated utilization is already visible in the table, not duplicated."""
    report = _report()
    for identifier in ("first", "second"):
        report.findings.append(
            PerformanceFinding(
                finding_code=PerformanceFindingCode.CAPACITY_HEADROOM,
                severity=PerformanceFindingSeverity.INFO,
                title="Есть запас пропускной способности",
                description="Расчётная нагрузка ниже порога насыщения.",
                affected_node_identifiers=[identifier],
            )
        )
    count_before = len(report.findings)
    text = "\n".join(
        page.extract_text()
        for page in PdfReader(
            BytesIO(PerformanceReportPdfRenderer().render(report))
        ).pages
    )

    assert "Есть запас пропускной способности" not in text
    assert len(report.findings) == count_before


def test_only_available_metric_columns_are_rendered() -> None:
    """No unavailable workload columns in a capacity-only scenario."""
    report = PerformanceAnalysisReport(
        scenario_identifier="capacity_only",
        status=PerformanceAnalysisStatus.UNAVAILABLE,
        nodes=[
            NodePerformanceMetrics(
                node_identifier="api",
                estimated_capacity_requests_per_second=25.0,
            )
        ],
    )
    text = "\n".join(
        page.extract_text()
        for page in PdfReader(
            BytesIO(PerformanceReportPdfRenderer().render(report))
        ).pages
    )

    assert "api" in text
    assert "25.00" in text
    assert "Нагрузка" not in text
    assert "Ожидание" not in text
    assert "Ответ," not in text
    assert "Недоступен" not in text


def test_confirmed_overload_is_visible_without_unrelated_warning() -> None:
    """A model-computed capacity risk remains visible without diagnostic noise."""
    report = _report()
    overload = PerformanceFinding(
        finding_code=PerformanceFindingCode.CAPACITY_SATURATION,
        severity=PerformanceFindingSeverity.ERROR,
        title="Перегрузка компонента",
        description="Расчётная загрузка 120%.",
        affected_node_identifiers=["api_0"],
    )
    report.findings.append(overload)
    text = "\n".join(
        page.extract_text()
        for page in PdfReader(
            BytesIO(PerformanceReportPdfRenderer().render(report))
        ).pages
    )

    assert overload.title in text
    assert overload.description in text
    assert report.findings[0].title not in text
