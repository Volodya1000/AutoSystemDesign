"""Extract source-grounded requirements and write a pipeline-compatible YAML scenario."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from application.document_scenario_service import DocumentScenarioService
from application.requirements_extraction import DocumentRequirementsService
from config.root import load_app_settings
from infrastructure.document_readers.markdown_reader import MarkdownReader
from infrastructure.llm.document_requirement_extractor import (
    LlmDocumentRequirementExtractor,
)
from infrastructure.llm.document_scenario_mapper import LlmDocumentScenarioMapper


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface for document-to-scenario generation."""
    parser = argparse.ArgumentParser(
        description="Extract verified requirements and create a pipeline-ready scenario."
    )
    parser.add_argument(
        "--document",
        type=Path,
        default=Path("examples/requirements/online_store.md"),
        help="Path to a UTF-8 Markdown document.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/document_scenario.yaml"),
        help="Path for the generated DesignScenario YAML.",
    )
    parser.add_argument(
        "--evidence-output",
        type=Path,
        default=None,
        help="Path for the JSON evidence manifest (default: <output-stem>.evidence.json).",
    )
    return parser


def _write_evidence_manifest(path: Path, result: DocumentScenarioResult) -> None:
    """Persist citations and diagnostics even when no safe scenario can be produced."""
    payload = {
        "source_name": result.source_name,
        "is_relevant": result.is_relevant,
        "field_evidence": result.field_evidence,
        "issues": [issue.model_dump(mode="json") for issue in result.issues],
        "scenario_created": result.scenario is not None,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run extraction, save evidence diagnostics, and write canonical scenario YAML."""
    args = build_parser().parse_args(argv)
    evidence_output: Path = args.evidence_output or args.output.with_name(
        f"{args.output.stem}.evidence.json"
    )

    try:
        settings = load_app_settings()
        requirement_extractor = LlmDocumentRequirementExtractor(settings)
        requirements_service = DocumentRequirementsService(
            reader=MarkdownReader(),
            extractor=requirement_extractor,
        )
        service = DocumentScenarioService(
            requirements_service=requirements_service,
            mapper=LlmDocumentScenarioMapper(settings),
        )
        result = service.extract_file(args.document)
        _write_evidence_manifest(evidence_output, result)
    except (OSError, ValueError) as error:
        print(f"Document-to-scenario extraction failed: {error}", file=sys.stderr)
        return 2

    if result.scenario is None:
        print(
            "No pipeline scenario was written because required fields or source "
            f"evidence could not be validated. Inspect {evidence_output}.",
            file=sys.stderr,
        )
        return 1

    output_payload = result.scenario.model_dump(
        mode="json", exclude_unset=True, exclude_none=True
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(output_payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"Generated scenario: {args.output}")
    print(f"Evidence manifest: {evidence_output}")
    print(f"Functional requirements: {len(result.scenario.functional_requirements)}")
    print(f"Non-functional requirements: {len(result.scenario.requirements)}")
    print(f"Diagnostics: {len(result.issues)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
