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
from infrastructure.performance_analysis.pdf_diagnostics import diagnostic_cards

if TYPE_CHECKING:
    from reportlab.pdfgen.canvas import Canvas

    from domain.performance_analysis.report import PerformanceAnalysisReport

_FONT_NAME = "ASDPerformanceSans"
_FONT_PATHS: tuple[Path, ...] = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/local/share/fonts/DejaVuSans.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("/Library/Fonts/Arial Unicode.ttf"),
)
_EMPTY_METRIC = "нет оценки"
_STATUS_LABELS: dict[str, str] = {
    "complete": "Доступные характеристики рассчитаны с учётом допущений",
    "partial": "Расчёты выполнены, но не все характеристики удалось проверить",
    "unavailable": "Недоступен: для расчётов недостаточно исходных данных",
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
                f"Результат: {_STATUS_LABELS[report.status.value]}",
                styles["body"],
            ),
            Spacer(1, 4 * mm),
            Paragraph("Сводка", styles["heading"]),
            Paragraph(
                "Максимальная оценка средней задержки синхронного пути: "
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
            Paragraph("Показатели обрабатывающих компонентов", styles["heading"]),
            Paragraph(
                "Нагрузка показывает число поступающих запросов в секунду. "
                "Пропускная способность — сколько запросов в секунду "
                "компонент теоретически способен обработать. Загрузка — "
                "отношение нагрузки к пропускной способности.",
                styles["note"],
            ),
        ]
        headers = (
            "Компонент",
            "Нагрузка,<br/>запр./с",
            "Пропускная<br/>способность,<br/>запр./с",
            "Загрузка",
            "Ожидание,<br/>мс",
            "Ответ,<br/>мс",
        )
        rows: list[list[Paragraph]] = [
            [Paragraph(cell, styles["table_header"]) for cell in headers]
        ]
        for node in report.nodes:
            if node.estimated_capacity_requests_per_second is None:
                # Clients generate traffic; they are not processing components.
                continue
            values = (
                escape(node.node_identifier),
                _metric(node.incoming_requests_per_second),
                _metric(node.estimated_capacity_requests_per_second),
                _metric(node.utilization_ratio, percent=True),
                _metric(node.estimated_mean_queue_wait_milliseconds),
                _metric(node.estimated_mean_response_time_milliseconds),
            )
            rows.append([Paragraph(value, styles["cell"]) for value in values])
        table = LongTable(
            rows,
            colWidths=[
                _CONTENT_WIDTH * portion
                for portion in (0.235, 0.14, 0.22, 0.115, 0.145, 0.145)
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
            [
                Spacer(1, 5 * mm),
                Paragraph("Выводы и ограничения", styles["heading"]),
                *diagnostic_cards(report, styles, _CONTENT_WIDTH),
            ]
        )
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
                    "Модель предполагает случайный поток поступления запросов "
                    "и использует приближённую формулу Аллена — Каннина. "
                    "Среднее время ответа само по себе не подтверждает p95/p99.",
                    styles["body"],
                ),
                Paragraph(
                    "Ограничение длины очереди, неизвестное число параллельно "
                    "обрабатываемых запросов и перегрузка могут делать "
                    "некоторые расчёты неприменимыми. Отсутствие оценки "
                    "не означает нулевое время ожидания.",
                    styles["body"],
                ),
                Paragraph(
                    "Если система одновременно обращается к нескольким сервисам, "
                    "ответ завершится после самого медленного из них. "
                    "Поэтому максимальная оценка средней задержки пути "
                    "не является точным средним временем ответа всей системы.",
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
        candidates = (self._font_path,) if self._font_path is not None else _FONT_PATHS
        font_path = next((path for path in candidates if path.is_file()), None)
        if font_path is None:
            message = (
                "A Unicode TrueType font is required for the PDF report. "
                "Pass font_path to PerformanceReportPdfRenderer."
            )
            raise PdfFontUnavailableError(message)
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
        "note": ParagraphStyle("ASDNote", parent=base, fontSize=7, leading=10),
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
