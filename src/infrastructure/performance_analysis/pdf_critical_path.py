"""Vertical, paginated critical-path visualization using only JSON report values.

The diagram is presentation-only. It never estimates network latency,
service time, node types or any metric absent from the canonical report.
"""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import LongTable, Paragraph, Table, TableStyle

if TYPE_CHECKING:
    from reportlab.platypus import Flowable

    from domain.performance_analysis.report import (
        NodePerformanceMetrics,
        PerformanceAnalysisReport,
    )

_BOX_COLOR = colors.HexColor("#EEF4FA")
_SOURCE_COLOR = colors.HexColor("#E7F3ED")
_OUTLINE_COLOR = colors.HexColor("#C7D6E5")


def critical_path_diagram(
    report: PerformanceAnalysisReport,
    styles: dict[str, ParagraphStyle],
    content_width: float,
) -> list[Flowable]:
    """Return a portrait-friendly vertical chain split between whole nodes."""
    if (
        report.estimated_longest_synchronous_path_mean_milliseconds is None
        or not report.critical_path_node_identifiers
    ):
        return []

    metrics_by_id: dict[str, NodePerformanceMetrics] = {
        node.node_identifier: node for node in report.nodes
    }
    width: float = content_width * 0.58
    arrow_style = ParagraphStyle(
        "ASDPathArrow",
        parent=styles["body"],
        alignment=TA_CENTER,
        fontSize=10,
        leading=11,
        spaceAfter=0,
    )
    rows: list[list[Flowable | list[Flowable]]] = []
    for index, identifier in enumerate(report.critical_path_node_identifiers):
        node: NodePerformanceMetrics | None = metrics_by_id.get(identifier)
        details: list[Flowable] = [Paragraph(escape(identifier), styles["path_node"])]
        if index == 0 and (
            node is None or node.estimated_capacity_requests_per_second is None
        ):
            details.append(Paragraph("Начало пути", styles["path_meta"]))
        if node is not None:
            if node.estimated_mean_response_time_milliseconds is not None:
                details.append(
                    Paragraph(
                        "Среднее время в узле: "
                        f"{node.estimated_mean_response_time_milliseconds:.2f} мс",
                        styles["path_meta"],
                    )
                )
            if node.estimated_mean_queue_wait_milliseconds is not None:
                details.append(
                    Paragraph(
                        "Из них ожидание: "
                        f"{node.estimated_mean_queue_wait_milliseconds:.2f} мс",
                        styles["path_meta"],
                    )
                )

        box = Table([[details]], colWidths=[width], hAlign="CENTER")
        box.setStyle(
            TableStyle(
                [
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, -1),
                        _SOURCE_COLOR if index == 0 else _BOX_COLOR,
                    ),
                    ("BOX", (0, 0), (-1, -1), 0.6, _OUTLINE_COLOR),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        cell: list[Flowable] = [box]
        if index < len(report.critical_path_node_identifiers) - 1:
            cell.append(Paragraph("↓", arrow_style))
        rows.append([cell])

    diagram = LongTable(rows, colWidths=[width], hAlign="CENTER")
    diagram.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return [diagram]
