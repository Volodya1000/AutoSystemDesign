"""Generate all architecture artifacts from one Markdown BRD."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

from config.logging import configure_logging
from infrastructure.document_generation import (
    DocumentGenerationOptions,
    generate_from_document,
)
from scripts._cli_arguments import add_visualisation_arguments

if TYPE_CHECKING:
    from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    """Describe the single-command BRD workflow."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document", type=Path, required=True)
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="Output directory (default: output/<document-stem>)",
    )
    parser.add_argument(
        "--profiles",
        type=Path,
        help="Optional explicit service profiles for reproducible calculations",
    )
    parser.add_argument("--verbose", action="store_true")
    add_visualisation_arguments(parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse CLI options and delegate the workflow."""
    args = build_parser().parse_args(argv)
    configure_logging(verbose=args.verbose)
    out_dir: Path = args.out_dir or Path("output") / args.document.stem
    return generate_from_document(
        DocumentGenerationOptions(
            document=args.document,
            out_dir=out_dir,
            profiles=args.profiles,
            diagram_server=args.diagram_server,
            diagram_format=args.diagram_format,
            render_diagrams=not args.no_diagram,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
