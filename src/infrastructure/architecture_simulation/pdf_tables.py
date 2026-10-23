"""Format canonical values and wrap report tables consistently."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

from reportlab.lib import colors
from reportlab.platypus import LongTable, Paragraph, TableStyle

if TYPE_CHECKING:
    from reportlab.lib.styles import ParagraphStyle


def number_text(value: float | None) -> str:
    """Distinguish a missing measurement from a measured zero."""
    return "нет данных" if value is None else f"{value:.2f}"


def ratio_text(value: float | None) -> str:
    """Format a measured fraction as a percentage."""
    return "нет данных" if value is None else f"{value:.2%}"


def report_table(
    rows: list[list[str]], styles: dict[str, ParagraphStyle], width: float
) -> LongTable:
    """Wrap cells and repeat the header on subsequent pages."""
    cells: list[list[Paragraph]] = [
        [Paragraph(escape(cell), styles["cell"]) for cell in row] for row in rows
    ]
    table: LongTable = LongTable(
        cells, colWidths=[width / len(rows[0])] * len(rows[0]), repeatRows=1
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF0F6")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#BDCAD8")),
            ]
        )
    )
    return table
