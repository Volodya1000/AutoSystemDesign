"""Readable PDF presentation for performance diagnostics.

Machine codes are deliberately preserved in JSON and hidden in the PDF.
This module only groups and styles existing conclusions; it makes no new
claims about capacity, latency or the probability of dropped requests.
"""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

from reportlab.lib import colors
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from domain.performance_analysis.report import (
    PerformanceFindingCode,
    PerformanceFindingSeverity,
)

if TYPE_CHECKING:
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Flowable

    from domain.performance_analysis.report import (
        PerformanceAnalysisReport,
        PerformanceFinding,
    )

_SEVERITY_LABELS: dict[PerformanceFindingSeverity, str] = {
    PerformanceFindingSeverity.WARNING: "Предупреждение",
    PerformanceFindingSeverity.INFO: "Информация",
    PerformanceFindingSeverity.ERROR: "Проблема",
}
_CARD_COLORS: dict[PerformanceFindingSeverity, tuple[str, str]] = {
    PerformanceFindingSeverity.WARNING: ("#FFF1F2", "#BE5365"),
    PerformanceFindingSeverity.INFO: ("#EDF8F1", "#4A9071"),
    PerformanceFindingSeverity.ERROR: ("#FCE6E9", "#AA334D"),
}


def visible_findings(report: PerformanceAnalysisReport) -> list[PerformanceFinding]:
    """Condense repeated headroom notices without changing the JSON payload."""
    headroom = [
        item
        for item in report.findings
        if item.finding_code is PerformanceFindingCode.CAPACITY_HEADROOM
    ]
    if len(headroom) < 2:
        return list(report.findings)

    affected = sorted(
        {
            identifier
            for item in headroom
            for identifier in item.affected_node_identifiers
        }
    )
    summary = headroom[0].model_copy(
        update={
            "title": "Есть запас пропускной способности",
            "description": (
                "Расчётная нагрузка перечисленных компонентов ниже "
                "предупреждающего порога 98%. Подробные значения показаны "
                "в таблице. Это не заменяет проверку реальной нагрузки."
            ),
            "affected_node_identifiers": affected,
            "recommendation": None,
        }
    )
    other = [
        item
        for item in report.findings
        if item.finding_code is not PerformanceFindingCode.CAPACITY_HEADROOM
    ]
    return [*other, summary]


def diagnostic_card(
    finding: PerformanceFinding,
    styles: dict[str, ParagraphStyle],
    content_width: float,
) -> Flowable:
    """Create a calm, accessible colored diagnostic card with Russian labels."""
    background, accent = _CARD_COLORS[finding.severity]
    heading = _SEVERITY_LABELS[finding.severity]
    body: list[Flowable] = [
        Paragraph(
            f"<b>{escape(heading)}: {escape(finding.title)}</b>",
            styles["finding"],
        )
    ]
    if finding.affected_node_identifiers:
        body.append(
            Paragraph(
                "Компоненты: "
                + escape(", ".join(finding.affected_node_identifiers)),
                styles["note"],
            )
        )
    body.append(Paragraph(escape(finding.description), styles["body"]))
    if finding.recommendation is not None:
        body.append(
            Paragraph(
                "<b>Что сделать:</b> " + escape(finding.recommendation),
                styles["body"],
            )
        )
    table = Table([[body]], colWidths=[content_width], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(background)),
                ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor(accent)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def diagnostic_cards(
    report: PerformanceAnalysisReport,
    styles: dict[str, ParagraphStyle],
    content_width: float,
) -> list[Flowable]:
    """Return styled cards separated by modest, readable vertical space."""
    if not report.findings:
        return [Paragraph("Диагностических выводов нет.", styles["body"])]

    cards: list[Flowable] = []
    for finding in visible_findings(report):
        cards.append(diagnostic_card(finding, styles, content_width))
        cards.append(Spacer(1, 3 * 2.8346456693))
    return cards
