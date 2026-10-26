"""BRD-to-artifacts workflow used by the thin script entry point."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

import yaml

from application.run_report import (
    DocumentRunReport,
    PerformanceInputMode,
    RunStageReport,
    RunStatus,
)
from config.root import load_app_settings
from domain.service_profiles import ServiceProfileCatalog
from infrastructure.composition import build_document_scenario_service
from infrastructure.exceptions.llm_exceptions import LlmConnectionError
from infrastructure.persistence.document_scenario import (
    scenario_payload,
    write_evidence_manifest,
)
from infrastructure.pipeline_execution import (
    PipelineExecutionOptions,
    execute_pipeline,
)
from infrastructure.reporting import LoggingPipelineReporter
from infrastructure.visualisation.plantuml import DiagramImageFormat

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from application.pipeline.outcome import StageOutcome

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DocumentGenerationOptions:
    """Inputs for one isolated BRD generation run."""

    document: Path
    out_dir: Path
    profiles: Path | None = None
    diagram_server: str | None = None
    diagram_format: DiagramImageFormat | None = None
    render_diagrams: bool = True


class RunReporter:
    """Collect stage results while preserving the console summary."""

    def __init__(self) -> None:
        self.stages: list[RunStageReport] = []

    def report(self, outcomes: Sequence[StageOutcome[object]]) -> None:
        """Record stage status, resource use, and diagnostics."""
        LoggingPipelineReporter().report(outcomes)
        self.stages = [
            RunStageReport(
                name=outcome.name,
                status=outcome.status,
                duration_seconds=outcome.duration_seconds,
                total_tokens=outcome.total_tokens,
                warnings=list(outcome.warnings),
                message=outcome.message,
            )
            for outcome in outcomes
        ]


def _artifact_files(directory: Path) -> list[str]:
    return sorted(
        str(path.relative_to(directory))
        for path in directory.rglob("*")
        if path.is_file() and path.name != "run.json"
    )


def _write_run_report(
    options: DocumentGenerationOptions,
    reporter: RunReporter,
    exit_code: int,
    failure: str | None,
) -> None:
    input_mode = (
        PerformanceInputMode.EXPLICIT_PROFILES
        if options.profiles is not None
        else PerformanceInputMode.GENERATED_C4
    )
    report = DocumentRunReport(
        source=str(options.document),
        exit_code=exit_code,
        status=RunStatus.COMPLETED if exit_code == 0 else RunStatus.FAILED,
        performance_input_mode=input_mode,
        artifacts=_artifact_files(options.out_dir),
        stages=reporter.stages,
        error=failure,
    )
    (options.out_dir / "run.json").write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def generate_from_document(options: DocumentGenerationOptions) -> int:
    """Extract verified requirements and run every architecture stage."""
    try:
        options.out_dir.mkdir(parents=True, exist_ok=False)
    except OSError:
        _LOGGER.exception(
            "Choose a new, writable output directory: %s", options.out_dir
        )
        return 2

    reporter = RunReporter()
    exit_code = 2
    failure: str | None = None
    try:
        settings = load_app_settings()
        if options.profiles is not None:
            settings.service_profiles = ServiceProfileCatalog.model_validate_json(
                options.profiles.read_text(encoding="utf-8")
            )
        result = build_document_scenario_service(settings).extract_file(
            options.document
        )
        write_evidence_manifest(options.out_dir / "requirements.evidence.json", result)
        if result.scenario is None:
            _LOGGER.error("No verified scenario; inspect requirements.evidence.json")
            exit_code = 1
        else:
            (options.out_dir / "scenario.yaml").write_text(
                yaml.safe_dump(
                    scenario_payload(result.scenario),
                    allow_unicode=True,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            _LOGGER.info(
                "Extracted %d functional requirements, %d NFRs, %d diagnostics",
                len(result.scenario.functional_requirements),
                len(result.scenario.requirements),
                len(result.issues),
            )
            exit_code = execute_pipeline(
                result.scenario,
                settings,
                PipelineExecutionOptions(
                    out_dir=options.out_dir / "artifacts",
                    diagram_server=(
                        options.diagram_server or settings.visualisation.server
                    ),
                    diagram_format=(
                        options.diagram_format
                        or DiagramImageFormat(settings.visualisation.image_format)
                    ),
                    render_diagrams=options.render_diagrams,
                ),
                reporter=reporter,
            )
    except (LlmConnectionError, OSError, ValueError) as error:
        failure = str(error)
        _LOGGER.exception("BRD generation failed")
    finally:
        _write_run_report(options, reporter, exit_code, failure)
        _LOGGER.info("Run report: %s", options.out_dir / "run.json")
    return exit_code
