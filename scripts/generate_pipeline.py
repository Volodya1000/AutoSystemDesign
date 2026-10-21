"""Pipeline runner: C4 Architecture -> Sequence Diagrams (N+1).

Usage (from the repository root, with LM Studio running):
    uv run scripts/generate_pipeline.py --scenario scenarios/ecommerce_checkout.yaml
    uv run scripts/generate_pipeline.py --scenario scenarios/x.yaml --out-dir output
    uv run scripts/generate_pipeline.py --scenario scenarios/x.yaml \
        --diagram-server kroki
    uv run scripts/generate_pipeline.py --scenario scenarios/x.yaml --no-diagram
    uv run scripts/generate_pipeline.py --scenario scenarios/x.yaml --verbose

CLI flags override visualisation settings from config.yaml.

Exit codes:
    0 - all required artifacts produced; PARTIAL (diagram failures only)
        is still 0 because diagrams are best-effort. Inspect the summary
        line for the exact status.
    1 - a required stage failed (missing JSON/AST artifacts).
    2 - configuration, scenario, or LLM endpoint failure.
"""

from __future__ import annotations

import argparse
import logging
import sys
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING, assert_never

import yaml
from pydantic import ValidationError

from application.pipeline.outcome import StageStatus
from config.logging import configure_logging
from config.root import AppSettings, load_app_settings
from domain.models import DesignScenario
from infrastructure.composition import build_pipeline
from infrastructure.exceptions.llm_exceptions import LlmConnectionError
from infrastructure.reporting import log_header
from infrastructure.visualisation.plantuml import DiagramImageFormat

if TYPE_CHECKING:
    from application.pipeline.result import PipelineRunResult

_logger: logging.Logger = logging.getLogger("pipeline")


class PipelineExitCode(IntEnum):
    """Public CLI exit codes with stable numeric values."""

    SUCCESS = 0
    STAGE_FAILURE = 1
    INPUT_OR_CONNECTION_ERROR = 2


def _exit_code_for_status(status: StageStatus) -> PipelineExitCode:
    """Convert a stage status to a CLI exit code in exactly one place."""
    match status:
        case StageStatus.SUCCEEDED | StageStatus.PARTIAL:
            return PipelineExitCode.SUCCESS
        case StageStatus.FAILED:
            return PipelineExitCode.STAGE_FAILURE
        case _:
            assert_never(status)


def main() -> PipelineExitCode:
    args: argparse.Namespace = _parse_args()
    configure_logging(verbose=args.verbose)

    try:
        settings: AppSettings = load_app_settings()
    except (ValidationError, ValueError):
        _logger.exception("Settings error")
        return PipelineExitCode.INPUT_OR_CONNECTION_ERROR

    try:
        scenario: DesignScenario = _load_scenario(args.scenario)
    except (OSError, yaml.YAMLError, ValidationError):
        _logger.exception("Scenario error")
        return PipelineExitCode.INPUT_OR_CONNECTION_ERROR

    out_dir, server, image_format = _resolve_visualisation(args, settings)
    out_dir.mkdir(parents=True, exist_ok=True)

    log_header(settings, scenario)

    try:
        wiring = build_pipeline(
            settings=settings,
            diagram_server=server,
            image_format=image_format,
            render_diagrams=not args.no_diagram,
        )
        result: PipelineRunResult = wiring.runner.run(scenario, out_dir, wiring.writer)
        return _exit_code_for_status(result.status)
    except LlmConnectionError:
        _logger.exception("LLM endpoint failure")
        return PipelineExitCode.INPUT_OR_CONNECTION_ERROR


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full design pipeline.")
    parser.add_argument(
        "--scenario", type=str, required=True, help="Path to scenario YAML"
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default=None,
        help="Override visualisation.diagram_dir from config.yaml",
    )
    parser.add_argument(
        "--diagram-server",
        type=str,
        default=None,
        help=(
            "Override visualisation.server "
            "(auto/plantuml/kroki or a plantuml-server URL)"
        ),
    )
    parser.add_argument(
        "--diagram-format",
        type=DiagramImageFormat,
        choices=[fmt.value for fmt in DiagramImageFormat],
        default=None,
        help="Override visualisation.image_format (png/svg)",
    )
    parser.add_argument(
        "--no-diagram", action="store_true", help="Skip diagram rendering"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="DEBUG logging: shows the raw LLM output of every completion",
    )
    return parser.parse_args()


def _load_scenario(path: str) -> DesignScenario:
    with Path(path).open("r", encoding="utf-8") as stream:
        return DesignScenario.model_validate(yaml.safe_load(stream))


def _resolve_visualisation(
    args: argparse.Namespace, settings: AppSettings
) -> tuple[Path, str, DiagramImageFormat]:
    v = settings.visualisation
    return (
        Path(args.out_dir or v.diagram_dir),
        args.diagram_server or v.server,
        DiagramImageFormat(args.diagram_format or v.image_format),
    )


if __name__ == "__main__":
    sys.exit(main())
