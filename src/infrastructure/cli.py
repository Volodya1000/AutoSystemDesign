"""Generate architecture artifacts directly from a BRD document."""

import argparse
import json
import logging
from collections.abc import Sequence
from pathlib import Path

import yaml

from application.document_scenario_service import DocumentScenarioService
from application.pipeline.outcome import StageOutcome
from application.requirements_extraction import DocumentRequirementsService
from config.logging import configure_logging
from config.root import load_app_settings
from domain.scenario_extraction import DocumentScenarioResult
from domain.service_profiles import ServiceProfileCatalog
from infrastructure.composition import build_pipeline
from infrastructure.document_readers.markdown_reader import MarkdownReader
from infrastructure.exceptions.llm_exceptions import LlmConnectionError
from infrastructure.llm.document_requirement_extractor import (
    LlmDocumentRequirementExtractor,
)
from infrastructure.llm.document_scenario_mapper import LlmDocumentScenarioMapper
from infrastructure.persistence.document_scenario import (
    scenario_payload,
    write_evidence_manifest,
)
from infrastructure.reporting import LoggingPipelineReporter
from infrastructure.visualisation.plantuml import DiagramImageFormat

_logger = logging.getLogger(__name__)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="BRD to architecture artifacts")
    generate.add_argument("--brd", type=Path, required=True)
    generate.add_argument("--out", type=Path, required=True)
    generate.add_argument("--diagram-server")
    generate.add_argument("--diagram-format", choices=["png", "svg"])
    generate.add_argument("--profiles", type=Path)
    generate.add_argument("--no-diagram", action="store_true")
    generate.add_argument("--verbose", action="store_true")
    return parser


def _write_extraction(result: DocumentScenarioResult, out: Path) -> None:
    """Keep source evidence and the canonical scenario alongside artifacts."""
    write_evidence_manifest(out / "requirements.evidence.json", result)
    if result.scenario is not None:
        (out / "scenario.yaml").write_text(
            yaml.safe_dump(
                scenario_payload(result.scenario), allow_unicode=True, sort_keys=False
            ),
            encoding="utf-8",
        )


class RunReporter:
    """Save stage statuses without discarding the console pipeline summary."""

    def __init__(self) -> None:
        self.stages: list[dict[str, object]] = []

    def report(self, outcomes: Sequence[StageOutcome[object]]) -> None:
        """Record exactly the stages and artifacts produced by this run."""
        LoggingPipelineReporter().report(outcomes)
        self.stages = [
            {
                "name": outcome.name.value,
                "status": outcome.status.value,
                "duration_seconds": outcome.duration_seconds,
                "total_tokens": outcome.total_tokens,
                "warnings": list(outcome.warnings),
                "message": outcome.message,
            }
            for outcome in outcomes
        ]


def _generate(args: argparse.Namespace, reporter: RunReporter) -> int:
    """Use one configuration and the existing services for every stage."""
    settings = load_app_settings()
    if args.profiles is not None:
        settings.service_profiles = ServiceProfileCatalog.model_validate_json(
            args.profiles.read_text(encoding="utf-8")
        )
    service = DocumentScenarioService(
        requirements_service=DocumentRequirementsService(
            reader=MarkdownReader(),
            extractor=LlmDocumentRequirementExtractor(settings),
        ),
        mapper=LlmDocumentScenarioMapper(settings),
    )
    result = service.extract_file(args.brd)
    _write_extraction(result, args.out)
    if result.scenario is None:
        _logger.error("No verified scenario; inspect requirements.evidence.json")
        return 1
    _logger.info(
        "Extracted %d functional requirements, %d NFRs, %d diagnostics",
        len(result.scenario.functional_requirements),
        len(result.scenario.requirements),
        len(result.issues),
    )
    wiring = build_pipeline(
        settings=settings,
        diagram_server=args.diagram_server or settings.visualisation.server,
        image_format=DiagramImageFormat(
            args.diagram_format or settings.visualisation.image_format
        ),
        render_diagrams=not args.no_diagram,
        pipeline_reporter=reporter,
    )
    return wiring.runner.run(result.scenario, args.out / "artifacts", wiring.writer)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the document workflow and preserve pipeline exit codes."""
    args = _parser().parse_args(argv)
    configure_logging(verbose=args.verbose)
    try:
        # A fresh directory prevents stale artifacts from looking like new results.
        args.out.mkdir(parents=True, exist_ok=False)
    except OSError:
        _logger.exception("Choose a new, writable output directory: %s", args.out)
        return 2
    exit_code = 2
    failure: str | None = None
    reporter = RunReporter()
    try:
        exit_code = _generate(args, reporter)
    except (LlmConnectionError, OSError, ValueError) as error:
        failure = str(error)
        _logger.exception("BRD generation failed")
    finally:
        files = sorted(
            str(path.relative_to(args.out))
            for path in args.out.rglob("*")
            if path.is_file()
        )
        summary = {
            "source": str(args.brd),
            "exit_code": exit_code,
            "status": "completed" if exit_code == 0 else "failed",
            "artifacts": files,
            "stages": reporter.stages,
            "error": failure,
            "note": "Completion does not imply all NFRs passed; see NFR coverage.",
        }
        (args.out / "run.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        _logger.info("Run report: %s", args.out / "run.json")
    return exit_code
