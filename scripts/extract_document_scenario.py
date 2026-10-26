"""Extract verified requirements into a pipeline-compatible YAML scenario."""

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

import yaml

from config.logging import configure_logging
from config.root import load_app_settings
from infrastructure.composition import build_document_scenario_service
from infrastructure.exceptions.llm_exceptions import LlmConnectionError
from infrastructure.persistence.document_scenario import (
    scenario_payload as _scenario_payload,
)
from infrastructure.persistence.document_scenario import (
    write_evidence_manifest as _write_evidence_manifest,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface for document-to-scenario generation."""
    parser = argparse.ArgumentParser(
        description="Extract verified requirements into a pipeline-ready scenario."
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
        help=(
            "Path for the JSON evidence manifest (default: "
            "<output-stem>.evidence.json)."
        ),
    )
    parser.add_argument(
        "--run-pipeline",
        action="store_true",
        help=(
            "Run the existing design pipeline after writing YAML and the "
            "evidence manifest."
        ),
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


def _run_pipeline(args: argparse.Namespace) -> int:
    """Invoke the existing pipeline CLI, keeping orchestration in one place."""
    logger = logging.getLogger(__name__)
    script_path = Path(__file__).with_name("generate_pipeline.py")
    command = [sys.executable, str(script_path), "--scenario", str(args.output)]
    if args.pipeline_out_dir is not None:
        command.extend(["--out-dir", str(args.pipeline_out_dir)])
    if args.no_diagram:
        command.append("--no-diagram")
    try:

        async def run_pipeline() -> int:
            process = await asyncio.create_subprocess_exec(*command)
            return await process.wait()

        return asyncio.run(run_pipeline())
    except OSError:
        logger.exception("Could not start the design pipeline")
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
        service = build_document_scenario_service(settings)
        result = service.extract_file(args.document)
        _write_evidence_manifest(evidence_output, result)
    except (LlmConnectionError, OSError, ValueError):
        logger.exception("Document-to-scenario extraction failed")
        return 2

    if result.scenario is None:
        logger.error(
            "No pipeline scenario was written because required fields or source "
            "evidence could not be validated. Inspect %s.",
            evidence_output,
        )
        return 1

    output_payload = _scenario_payload(result.scenario)
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
