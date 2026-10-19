"""Extract source-grounded requirements and write a pipeline-compatible YAML scenario."""

import argparse
import json
import logging
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import yaml

from application.document_scenario_service import DocumentScenarioService
from application.requirements_extraction import DocumentRequirementsService
from config.logging import configure_logging
from config.root import load_app_settings
from domain.scenario_extraction import DocumentScenarioResult
from infrastructure.document_readers.markdown_reader import MarkdownReader
from infrastructure.exceptions.llm_exceptions import LlmConnectionError
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
    parser.add_argument(
        "--run-pipeline",
        action="store_true",
        help="Run the existing design pipeline after writing YAML and the evidence manifest.",
    )
    parser.add_argument(
        "--pipeline-out-dir",
        type=Path,
        default=None,
        help="Optional output directory passed to generate_pipeline.py.",
    )
    parser.add_argument(
        "--no-diagram",
        action="store_true",
        help="Skip diagram rendering when --run-pipeline is enabled.",
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


def _run_pipeline(args: argparse.Namespace) -> int:
    """Invoke the existing pipeline CLI so its orchestration remains the single source."""
    logger = logging.getLogger(__name__)
    script_path = Path(__file__).with_name("generate_pipeline.py")
    command = [sys.executable, str(script_path), "--scenario", str(args.output)]
    if args.pipeline_out_dir is not None:
        command.extend(["--out-dir", str(args.pipeline_out_dir)])
    if args.no_diagram:
        command.append("--no-diagram")
    try:
        return subprocess.run(command, check=False).returncode
    except OSError as error:
        logger.error("Could not start the design pipeline: %s", error)
        return 2


def main(argv: Sequence[str] | None = None) -> int:
    """Run extraction, save evidence diagnostics, and write canonical scenario YAML."""
    configure_logging(verbose=False)
    logger = logging.getLogger(__name__)
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
    except (LlmConnectionError, OSError, ValueError) as error:
        logger.error("Document-to-scenario extraction failed: %s", error)
        return 2

    if result.scenario is None:
        logger.error(
            "No pipeline scenario was written because required fields or source "
            "evidence could not be validated. Inspect %s.",
            evidence_output,
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
    logger.info("Generated scenario: %s", args.output)
    logger.info("Evidence manifest: %s", evidence_output)
    logger.info(
        "Functional requirements: %d", len(result.scenario.functional_requirements)
    )
    logger.info("Non-functional requirements: %d", len(result.scenario.requirements))
    logger.info("Diagnostics: %d", len(result.issues))
    if args.run_pipeline:
        return _run_pipeline(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
