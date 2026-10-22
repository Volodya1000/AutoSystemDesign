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


def test_pdf_is_readable_and_contains_cyrillic_and_absent_metric() -> None:
    pdf_bytes = PerformanceReportPdfRenderer().render(_report())
    reader = PdfReader(BytesIO(pdf_bytes))
    text = "\n".join(page.extract_text() for page in reader.pages)

    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 2000
    assert "Анализ производительности" in text
    assert "load_test_пример" in text
    assert "Ограниченная очередь" in text
    assert "нет оценки" in text
    assert "15.00 мс" in text


def test_long_identifiers_and_many_rows_paginate() -> None:
    pdf_bytes = PerformanceReportPdfRenderer().render(_report(node_count=90))
    reader = PdfReader(BytesIO(pdf_bytes))
    text = "\n".join(page.extract_text() for page in reader.pages)

    assert len(reader.pages) > 1
    assert "api_89" in text
    assert "Выводы и ограничения" in text


def test_missing_font_reports_explicit_optional_failure(tmp_path: Path) -> None:
    renderer = PerformanceReportPdfRenderer(font_path=tmp_path / "absent.ttf")

    with pytest.raises(PdfFontUnavailableError, match="Unicode TrueType font"):
        renderer.render(_report())


def test_unavailable_report_shows_honest_missing_metrics() -> None:
    report = PerformanceAnalysisReport(
        scenario_identifier="no_workload",
        status=PerformanceAnalysisStatus.UNAVAILABLE,
    )
    reader = PdfReader(BytesIO(PerformanceReportPdfRenderer().render(report)))
    text = "\n".join(page.extract_text() for page in reader.pages)

    assert "Недоступен" in text
    assert "нет оценки" in text
    assert "Диагностических выводов нет" in text


def test_pdf_explains_findings_without_raw_machine_codes() -> None:
    """Keep diagnostic codes in JSON, while PDF uses accessible Russian text."""
    pdf_bytes = PerformanceReportPdfRenderer().render(_report())
    text = "\n".join(
        page.extract_text() for page in PdfReader(BytesIO(pdf_bytes)).pages
    )

    assert "[warning]" not in text
    assert "bounded_queue_unmodeled" not in text
    assert "Предупреждение" in text
    assert "Компоненты:" in text


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
    table_content = text.split("Показатели обрабатывающих компонентов", 1)[1]
    table_content = table_content.split("Выводы и ограничения", 1)[0]

    assert "client" not in table_content
    assert "Критический путь: client" in text


def test_repeated_headroom_diagnostics_are_combined_in_pdf() -> None:
    """Group repeated informational statements without mutating JSON findings."""
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

    assert text.count("Информация: Есть запас пропускной способности") == 1
    assert len(report.findings) == count_before
