"""Lay out the supplied physical C4 edges without changing their meaning."""

from __future__ import annotations

from typing import TYPE_CHECKING

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.pdfbase.pdfmetrics import stringWidth

if TYPE_CHECKING:
    from domain.architecture_simulation.graph_plan import GraphSimulationPlan

_LAYER_SPACING: float = 70.0
_NODE_WIDTH: float = 130.0
_NODE_HEIGHT: float = 28.0


def _positions(
    plan: GraphSimulationPlan, width: float
) -> dict[str, tuple[float, float]]:
    """Calculate visual DAG layers independently of drawing primitives."""
    levels: dict[str, int] = dict.fromkeys(plan.topological_order, 0)
    identifier: str
    for identifier in plan.topological_order:
        for edge in plan.connections:
            if edge.source_identifier == identifier:
                levels[edge.target_identifier] = max(
                    levels[edge.target_identifier], levels[identifier] + 1
                )
    layer_count: int = max(levels.values()) + 1
    positions: dict[str, tuple[float, float]] = {}
    for level in range(layer_count):
        members: list[str] = sorted(
            identifier for identifier, depth in levels.items() if depth == level
        )
        for index, identifier in enumerate(members):
            positions[identifier] = (
                width * (index + 1) / (len(members) + 1),
                20.0 + (layer_count - level - 1) * _LAYER_SPACING,
            )
    return positions


def _connections(
    drawing: Drawing,
    positions: dict[str, tuple[float, float]],
    plan: GraphSimulationPlan,
    node_height: float,
) -> None:
    """Draw only edges present in the canonical graph plan."""
    for edge in plan.connections:
        source_x: float
        source_y: float
        target_x: float
        target_y: float
        source_x, source_y = positions[edge.source_identifier]
        target_x, target_y = positions[edge.target_identifier]
        source_y -= node_height / 2
        target_y += node_height / 2
        drawing.add(Line(source_x, source_y, target_x, target_y))
        drawing.add(
            Polygon(
                [
                    target_x,
                    target_y,
                    target_x - 3,
                    target_y + 6,
                    target_x + 3,
                    target_y + 6,
                ],
                fillColor=colors.white,
            )
        )


def _label_lines(identifier: str, font: str, width: float) -> list[str]:
    """Wrap even unbroken identifiers at a readable font size."""
    lines: list[str] = []
    current: str = ""
    for character in identifier:
        if current and stringWidth(current + character, font, 9) > width:
            lines.append(current)
            current = ""
        current += character
    return [*lines, current]


def graph_drawing(plan: GraphSimulationPlan, width: float, font: str) -> Drawing:
    """Expand layers and wrap labels instead of overlapping or shrinking text."""
    positions: dict[str, tuple[float, float]] = _positions(plan, width)
    row_sizes: dict[float, int] = {}
    for _, y in positions.values():
        row_sizes[y] = row_sizes.get(y, 0) + 1
    node_width: float = min(_NODE_WIDTH, width / (max(row_sizes.values()) + 1) - 8)
    labels: dict[str, list[str]] = {
        identifier: _label_lines(identifier, font, node_width - 12)
        for identifier in positions
    }
    node_height: float = max(_NODE_HEIGHT, max(map(len, labels.values())) * 11 + 12)
    spacing: float = node_height + 30
    positions = {
        identifier: (x, node_height / 2 + 8 + (y - 20) * spacing / _LAYER_SPACING)
        for identifier, (x, y) in positions.items()
    }
    height: float = max(y for _, y in positions.values()) + node_height / 2 + 8
    drawing: Drawing = Drawing(width, height)
    _connections(drawing, positions, plan, node_height)
    _draw_cards(drawing, positions, labels, font, (node_width, node_height))
    return drawing


def _draw_cards(
    drawing: Drawing,
    positions: dict[str, tuple[float, float]],
    labels: dict[str, list[str]],
    font: str,
    size: tuple[float, float],
) -> None:
    """Draw readable wrapped labels inside non-overlapping cards."""
    node_width: float
    node_height: float
    node_width, node_height = size
    for identifier, (center_x, center_y) in positions.items():
        drawing.add(Rect(
            center_x - node_width / 2, center_y - node_height / 2,
            node_width, node_height, fillColor=colors.white,
        ))
        for index, line in enumerate(labels[identifier]):
            drawing.add(String(
                center_x, center_y + (len(labels[identifier]) - 1) * 5.5 - index * 11 - 3,
                line, textAnchor="middle", fontName=font, fontSize=9,
            ))
