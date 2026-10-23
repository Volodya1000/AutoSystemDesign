"""Render an architect's decision summary from the canonical simulation report."""

from __future__ import annotations

from html import escape
from io import BytesIO
from typing import TYPE_CHECKING

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate

from domain.architecture_simulation.report import SimulationReportStatus
from infrastructure.architecture_simulation.pdf_sections import (
    decision_sections,
    experiment_sections,
    limitations_text,
)
from infrastructure.reporting.pdf.typography import (
    UnicodeReportFont,
    build_report_styles,
    draw_report_footer,
)

if TYPE_CHECKING:
    from reportlab.lib.styles import ParagraphStyle

    from domain.architecture_simulation.offline import OfflineSimulationResult

_WIDTH: float = A4[0] - 36 * mm
_STATUS_NAMES: dict[SimulationReportStatus, str] = {
    SimulationReportStatus.COMPLETE: "полное покрытие",
    SimulationReportStatus.PARTIAL: "частичное покрытие",
    SimulationReportStatus.UNAVAILABLE: "расчет недоступен",
}


class SimulationReportPdfRenderer:
    """Lead with measured consequences and retain the relevant model assumptions."""

    def render(self, result: OfflineSimulationResult) -> bytes:
        """Return a searchable PDF without recalculating canonical statistics."""
        font: str = UnicodeReportFont().register()
        styles: dict[str, ParagraphStyle] = build_report_styles(font)
        buffer: BytesIO = BytesIO()
        document: SimpleDocTemplate = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=16 * mm,
            bottomMargin=18 * mm,
            title=f"SimPy: {result.report.scenario_identifier}",
            author="AutoSystemDesign",
        )
        story: list[Flowable] = [
            Paragraph("Имитационная проверка архитектуры", styles["title"]),
            Paragraph(escape(result.inputs.scenario.description), styles["body"]),
            Paragraph(
                f"{escape(result.report.scenario_identifier)} · "
                f"{_STATUS_NAMES[result.report.status]}. "
                "Результаты модели, не измерения работающих сервисов.",
                styles["note"],
            ),
        ]
        story.extend(decision_sections(result.report, styles, _WIDTH))
        notes: str = limitations_text(result.report)
        if notes:
            story.append(Paragraph(escape(notes), styles["note"]))
        story.extend(experiment_sections(result, styles, _WIDTH))
        document.build(
            story,
            onFirstPage=lambda canvas, _doc: draw_report_footer(canvas, font),
            onLaterPages=lambda canvas, _doc: draw_report_footer(canvas, font),
        )
        return buffer.getvalue()
