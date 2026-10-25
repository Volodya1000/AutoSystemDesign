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
from pathlib import Path

import yaml
from pydantic import ValidationError

from config.logging import configure_logging
from config.root import AppSettings, load_app_settings
from domain.models import DesignScenario
from domain.service_profiles import ServiceProfileCatalog
from infrastructure.cli_arguments import add_visualisation_arguments
from infrastructure.exceptions.llm_exceptions import LlmConnectionError
from infrastructure.pipeline_execution import PipelineExecutionOptions, execute_pipeline
from infrastructure.reporting import log_header
from infrastructure.visualisation.plantuml import DiagramImageFormat

_logger: logging.Logger = logging.getLogger("pipeline")


def main() -> int:
    args: argparse.Namespace = _parse_args()
    configure_logging(verbose=args.verbose)

    try:
        settings: AppSettings = load_app_settings()
        if args.profiles is not None:
            settings.service_profiles = ServiceProfileCatalog.model_validate_json(
                args.profiles.read_text(encoding="utf-8")
            )
    except (OSError, ValidationError, ValueError):
        _logger.exception("Settings error")
        return 2

    try:
        scenario: DesignScenario = _load_scenario(args.scenario)
    except ValidationError as error:
        _log_scenario_validation_errors(args.scenario, error)
        return 2
    except (OSError, yaml.YAMLError):
        _logger.exception("Scenario error")
        return 2

    out_dir, server, image_format = _resolve_visualisation(args, settings)
    out_dir.mkdir(parents=True, exist_ok=True)

    log_header(settings, scenario)

    try:
        return execute_pipeline(
            scenario,
            settings,
            PipelineExecutionOptions(
                out_dir=out_dir,
                diagram_server=server,
                diagram_format=image_format,
                render_diagrams=not args.no_diagram,
            ),
        )
    except LlmConnectionError:
        _logger.exception("LLM endpoint failure")
        return 2


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full design pipeline.")
    parser.add_argument(
        "--scenario", type=str, required=True, help="Path to scenario YAML"
    )
    parser.add_argument(
        "--profiles",
        type=Path,
        default=None,
        help="JSON catalog of explicit service parameters and their sources",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default=None,
        help="Override visualisation.diagram_dir from config.yaml",
    )
    add_visualisation_arguments(parser)
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="DEBUG logging: shows the raw LLM output of every completion",
    )
    return parser.parse_args()


def _log_scenario_validation_errors(path: str, error: ValidationError) -> None:
    """Report invalid YAML keys with their complete field paths."""
    for detail in error.errors():
        location = ".".join(str(part) for part in detail["loc"])
        description = (
            "Unknown field" if detail["type"] == "extra_forbidden" else detail["msg"]
        )
        _logger.error("Invalid scenario %s at '%s': %s", path, location, description)


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
