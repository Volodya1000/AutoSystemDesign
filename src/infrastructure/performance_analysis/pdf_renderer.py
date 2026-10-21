"""Render the canonical performance report as a readable, searchable PDF."""

from __future__ import annotations

from html import escape
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
)

from application.performance_analysis.protocols import PdfRenderingUnavailableError
from domain.performance_analysis.report import PerformanceAnalysisReport

if TYPE_CHECKING:
    from reportlab.pdfgen.canvas import Canvas

_FONT_NAME = "ASDPerformanceSans"
_FONT_PATHS: tuple[Path, ...] = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/local/share/fonts/DejaVuSans.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("/Library/Fonts/Arial Unicode.ttf"),
)
_EMPTY_METRIC = "нет оценки"
_STATUS_LABELS: dict[str, str] = {
    "complete": "Полный",
    "partial": "Частичный (есть ограничения модели)",
    "unavailable": "Недоступен (недостаточно исходных данных)",
}
_PAGE_WIDTH, _PAGE_HEIGHT = A4
_CONTENT_WIDTH = _PAGE_WIDTH - 36 * mm


class PdfFontUnavailableError(PdfRenderingUnavailableError):
    """No permitted Unicode TrueType font is accessible for embedding."""


class PerformanceReportPdfRenderer:
    """Turn a calculated report into PDF bytes without recalculating metrics.

    The PDF is a *presentation*, not a source of truth. Node metrics, findings
    and assumptions are already present in the canonical Pydantic report.
    Fonts are embedded from an installed, user-supplied system TrueType font;
    font files are never committed to the repository.
    """

    def __init__(self, font_path: Path | None = None) -> None:
        self._font_path = font_path

    def render(self, report: PerformanceAnalysisReport) -> bytes:
        """Return a paginated, selectable-text PDF containing report values."""
        font = self._register_font()
        styles = _build_styles(font)
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=20 * mm,
            bottomMargin=21 * mm,
            title=f"Анализ производительности: {report.scenario_identifier}",
            author="AutoSystemDesign",
        )
        story: list[Flowable] = [
            Paragraph("Анализ производительности", styles["title"]),
            Spacer(1, 5 * mm),
            Paragraph(
                f"Сценарий: {escape(report.scenario_identifier)}",
                styles["body"],
            ),
            Paragraph(
                f"Полнота анализа: {_STATUS_LABELS[report.status.value]}",
                styles["body"],
            ),
            Spacer(1, 4 * mm),
            Paragraph("Сводка", styles["heading"]),
            Paragraph(
                "Оценка самого длинного синхронного пути из средних задержек: "
                + _metric(
                    report.estimated_longest_synchronous_path_mean_milliseconds,
                    "мс",
                ),
                styles["body"],
            ),
            Paragraph(
                "Критический путь: "
                + (
                    escape(" -> ".join(report.critical_path_node_identifiers))
                    if report.critical_path_node_identifiers
                    else _EMPTY_METRIC
                ),
                styles["body"],
            ),
            Spacer(1, 3 * mm),
            Paragraph("Метрики узлов", styles["heading"]),
        ]
        headers = ("Узел", "RPS", "Мощн. RPS", "Доля", "Очередь, мс", "Ответ, мс")
        rows: list[list[Paragraph]] = [
            [Paragraph(cell, styles["table_header"]) for cell in headers]
        ]
        for node in report.nodes:
            values = (
                escape(node.node_identifier),
                _metric(node.incoming_requests_per_second),
                _metric(node.estimated_capacity_requests_per_second),
                _metric(node.utilization_ratio, percent=True),
                _metric(node.estimated_mean_queue_wait_milliseconds),
                _metric(node.estimated_mean_response_time_milliseconds),
            )
            rows.append(
                [Paragraph(value, styles["cell"]) for value in values]
            )
        table = LongTable(
            rows,
            colWidths=[
                _CONTENT_WIDTH * portion
                for portion in (0.25, 0.11, 0.16, 0.12, 0.18, 0.18)
            ],
            repeatRows=1,
            hAlign="LEFT",
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF0F6")),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#F7F9FC")],
                    ),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#BDCAD8")),
                ]
            )
        )
        story.append(table)
        story.extend(
            [Spacer(1, 5 * mm), Paragraph("Диагностические выводы", styles["heading"])]
        )
        if not report.findings:
            story.append(Paragraph("Диагностических выводов нет.", styles["body"]))
        for finding in report.findings:
            affected = ", ".join(finding.affected_node_identifiers) or "весь сценарий"
            story.extend(
                [
                    Paragraph(
                        escape(f"[{finding.severity.value}] {finding.title}"),
                        styles["finding"],
                    ),
                    Paragraph(
                        "Код: " + escape(finding.finding_code.value)
                        + "; узлы: " + escape(affected),
                        styles["note"],
                    ),
                    Paragraph(escape(finding.description), styles["body"]),
                ]
            )
            if finding.recommendation is not None:
                story.append(
                    Paragraph(
                        "Рекомендация: " + escape(finding.recommendation),
                        styles["body"],
                    )
                )
            story.append(Spacer(1, 2 * mm))
        story.extend(
            [
                Spacer(1, 4 * mm),
                Paragraph("Допущения и ограничения", styles["heading"]),
                Paragraph(
                    "Показатели представляют модельные оценки по исходным "
                    "параметрам архитектуры, а не измерения реального сервиса.",
                    styles["body"],
                ),
                Paragraph(
                    "Модель задержки предполагает пуассоновский поток поступлений "
                    "и использует аппроксимацию Аллена - Каннина. "
                    "Средние оценки не подтверждают p95/p99.",
                    styles["body"],
                ),
                Paragraph(
                    "Конечные буферы, неизвестные каналы обслуживания и "
                    "переполнение могут делать часть метрик неприменимой. "
                    "Значение «нет оценки» означает null в JSON, а не ноль.",
                    styles["body"],
                ),
                Paragraph(
                    "Максимум средних задержек путей не равен среднему времени "
                    "завершения параллельного fan-out.",
                    styles["body"],
                ),
            ]
        )
        doc.build(
            story,
            onFirstPage=lambda canvas, _document: _draw_footer(canvas, font),
            onLaterPages=lambda canvas, _document: _draw_footer(canvas, font),
        )
        return buffer.getvalue()

    def _register_font(self) -> str:
        """Register a font capable of embedding Russian and English text."""
        candidates = (
            (self._font_path,)
            if self._font_path is not None
            else _FONT_PATHS
        )
        font_path = next((path for path in candidates if path.is_file()), None)
        if font_path is None:
            raise PdfFontUnavailableError(
                "A Unicode TrueType font is required for the PDF report. "
                "Pass font_path to PerformanceReportPdfRenderer."
            )
        if _FONT_NAME not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(_FONT_NAME, str(font_path)))
        return _FONT_NAME


def _metric(
    value: float | None,
    unit: str = "",
    *,
    percent: bool = False,
) -> str:
    """Format a report value without conflating missing and zero."""
    if value is None:
        return _EMPTY_METRIC
    if percent:
        return f"{value:.1%}"
    return f"{value:,.2f}".replace(",", " ") + (f" {unit}" if unit else "")


def _build_styles(font: str) -> dict[str, ParagraphStyle]:
    """Define a small report-specific typographic scale."""
    base = ParagraphStyle(
        "ASDBody",
        fontName=font,
        fontSize=9,
        leading=14,
        spaceAfter=6,
        splitLongWords=1,
        wordWrap="CJK",
    )
    return {
        "body": base,
        "title": ParagraphStyle(
            "ASDTitle",
            parent=base,
            fontSize=16,
            leading=22,
            alignment=TA_CENTER,
            spaceAfter=7,
        ),
        "heading": ParagraphStyle(
            "ASDHeading", parent=base, fontSize=12, leading=17, spaceBefore=8
        ),
        "finding": ParagraphStyle(
            "ASDFinding", parent=base, fontSize=10, leading=15, spaceBefore=7
        ),
        "note": ParagraphStyle(
            "ASDNote", parent=base, fontSize=7, leading=10
        ),
        "cell": ParagraphStyle(
            "ASDCell", parent=base, fontSize=7, leading=10, spaceAfter=0
        ),
        "table_header": ParagraphStyle(
            "ASDTableHead", parent=base, fontSize=7, leading=10, spaceAfter=0
        ),
    }


def _draw_footer(canvas: Canvas, font: str) -> None:
    """Render deterministic page numbering below the document content."""
    canvas.saveState()
    canvas.setFont(font, 8)
    canvas.drawRightString(
        _PAGE_WIDTH - 18 * mm,
        12 * mm,
        f"AutoSystemDesign | страница {canvas.getPageNumber()}",
    )
    canvas.restoreState()
