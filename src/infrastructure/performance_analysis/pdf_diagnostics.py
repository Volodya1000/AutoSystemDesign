"""Render only confirmed, calculated capacity issues in the PDF.

Full diagnostics remain available in the machine-readable JSON report.
Unsupported-model notices and capacity-headroom repetitions are not
architectural findings to repeat in a concise human-facing PDF.
"""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from domain.performance_analysis.report import PerformanceFindingCode

if TYPE_CHECKING:
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Flowable

    from domain.performance_analysis.report import (
        PerformanceAnalysisReport,
        PerformanceFinding,
    )

_ISSUE_BACKGROUND = colors.HexColor("#FFF1F2")
_ISSUE_ACCENT = colors.HexColor("#BE5365")


def confirmed_capacity_issues(
    report: PerformanceAnalysisReport,
) -> list[PerformanceFinding]:
    """Keep only computed saturation findings, not unsupported-model notices."""
    return [
        finding
        for finding in report.findings
        if finding.finding_code is PerformanceFindingCode.CAPACITY_SATURATION
    ]


def diagnostic_cards(
    report: PerformanceAnalysisReport,
    styles: dict[str, ParagraphStyle],
    content_width: float,
) -> list[Flowable]:
    """Display actual capacity risks with a restrained visual treatment."""
    cards: list[Flowable] = []
    for finding in confirmed_capacity_issues(report):
        body: list[Flowable] = [
            Paragraph(escape(finding.title), styles["finding"]),
            Paragraph(escape(finding.description), styles["body"]),
        ]
        if finding.recommendation is not None:
            body.append(
                Paragraph(
                    "<b>Рекомендация:</b> " + escape(finding.recommendation),
                    styles["body"],
                )
            )

        table = Table([[body]], colWidths=[content_width], hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _ISSUE_BACKGROUND),
                    ("LINEBEFORE", (0, 0), (0, -1), 3, _ISSUE_ACCENT),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        cards.extend((table, Spacer(1, 3 * mm)))

    return cards
