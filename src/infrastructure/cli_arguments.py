"""Shared argparse types for pipeline entry points."""

from __future__ import annotations

import argparse
from urllib.parse import urlparse

from infrastructure.visualisation.plantuml import DiagramImageFormat

_DIAGRAM_SERVER_PRESETS = frozenset({"auto", "plantuml", "kroki"})


def diagram_server(value: str) -> str:
    """Accept a known renderer preset or an absolute HTTP(S) server URL."""
    if value in _DIAGRAM_SERVER_PRESETS:
        return value
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return value
    message = "expected auto, plantuml, kroki, or an absolute http(s) PlantUML URL"
    raise argparse.ArgumentTypeError(message)


def add_visualisation_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the rendering options shared by scenario and BRD commands."""
    parser.add_argument(
        "--diagram-server",
        type=diagram_server,
        default=None,
        help=(
            "Override visualisation.server: auto, plantuml, kroki, or an "
            "absolute http(s) PlantUML server URL"
        ),
    )
    parser.add_argument(
        "--diagram-format",
        type=DiagramImageFormat,
        choices=[item.value for item in DiagramImageFormat],
        default=None,
        help="Override visualisation.image_format (png/svg)",
    )
    parser.add_argument(
        "--no-diagram",
        action="store_true",
        help="Skip diagram rendering",
    )
