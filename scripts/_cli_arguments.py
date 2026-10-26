"""Argparse adapter shared only by executable scripts."""

from __future__ import annotations

import argparse

from infrastructure.visualisation.plantuml import DiagramImageFormat
from shared.diagram_server import (
    DiagramServerSelectionError,
    diagram_server_usage,
    normalize_diagram_server,
)


def diagram_server(value: str) -> str:
    """Validate a CLI value through the shared typed selection model."""
    try:
        selection = normalize_diagram_server(value)
    except DiagramServerSelectionError as error:
        raise argparse.ArgumentTypeError(diagram_server_usage()) from error
    return str(selection)


def add_visualisation_arguments(parser: argparse.ArgumentParser) -> None:
    """Add rendering options to one argparse entry point."""
    parser.add_argument(
        "--diagram-server",
        type=diagram_server,
        default=None,
        help=f"Override visualisation.server: {diagram_server_usage()}",
    )
    parser.add_argument(
        "--diagram-format",
        type=DiagramImageFormat,
        choices=list(DiagramImageFormat),
        default=None,
        help="Override visualisation.image_format",
    )
    parser.add_argument(
        "--no-diagram",
        action="store_true",
        help="Skip diagram rendering",
    )
