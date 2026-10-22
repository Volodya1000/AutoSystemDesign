"""Lay out the supplied physical C4 edges without changing their meaning."""

from __future__ import annotations

from typing import TYPE_CHECKING

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors

if TYPE_CHECKING:
    from domain.architecture_simulation.graph_plan import GraphSimulationPlan

_HEIGHT: float = 170.0
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
                _HEIGHT - 20.0 - level * (_HEIGHT - 50.0) / max(layer_count - 1, 1),
            )
    return positions


def _connections(
    drawing: Drawing,
    positions: dict[str, tuple[float, float]],
    plan: GraphSimulationPlan,
) -> None:
    """Draw only edges present in the canonical graph plan."""
    for edge in plan.connections:
        source_x: float
        source_y: float
        target_x: float
        target_y: float
        source_x, source_y = positions[edge.source_identifier]
        target_x, target_y = positions[edge.target_identifier]
        source_y -= _NODE_HEIGHT / 2
        target_y += _NODE_HEIGHT / 2
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


def graph_drawing(plan: GraphSimulationPlan, width: float, font: str) -> Drawing:
    """Place DAG layers vertically and draw the original physical edges."""
    positions: dict[str, tuple[float, float]] = _positions(plan, width)
    drawing: Drawing = Drawing(width, _HEIGHT)
    _connections(drawing, positions, plan)
    for identifier, (center_x, center_y) in positions.items():
        card: Rect = Rect(
            center_x - _NODE_WIDTH / 2,
            center_y - _NODE_HEIGHT / 2,
            _NODE_WIDTH,
            _NODE_HEIGHT,
        )
        card.fillColor = colors.white
        drawing.add(card)
        drawing.add(
            String(
                center_x,
                center_y - 3,
                identifier,
                textAnchor="middle",
                fontName=font,
                fontSize=9,
            )
        )
    return drawing
