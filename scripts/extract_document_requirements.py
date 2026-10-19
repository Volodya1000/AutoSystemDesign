"""Run document-requirements extraction against a local Markdown file."""

import argparse
import json
import logging
from collections.abc import Sequence
from pathlib import Path

from application.requirements_extraction import DocumentRequirementsService
from config.logging import configure_logging
from config.root import load_app_settings
from infrastructure.document_readers.markdown_reader import MarkdownReader
from infrastructure.exceptions.llm_exceptions import LlmConnectionError
from infrastructure.llm.document_requirement_extractor import (
    LlmDocumentRequirementExtractor,
)

_logger: logging.Logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface for raw requirement extraction."""
    parser = argparse.ArgumentParser(
        description="Extract functional and non-functional requirements from Markdown."
    )
    parser.add_argument(
        "--document",
        type=Path,
        default=Path("examples/requirements/online_store.md"),
        help="Path to a Markdown document (default: bundled online-store example).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/document_requirements.json"),
        help="Path for the JSON result.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Extract claims, validate their citations, and write JSON diagnostics."""
    configure_logging(verbose=False)
    args = build_parser().parse_args(argv)
    try:
        settings = load_app_settings()
        service = DocumentRequirementsService(
            reader=MarkdownReader(),
            extractor=LlmDocumentRequirementExtractor(settings),
        )
        result = service.extract_file(args.document)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
    except (LlmConnectionError, OSError, ValueError) as error:
        _logger.error("Document requirement extraction failed: %s", error)
        return 2

    _logger.info("Extracted %d requirements.", len(result.requirements))
    _logger.info("Reported %d diagnostic issues.", len(result.issues))
    _logger.info("JSON result: %s", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
