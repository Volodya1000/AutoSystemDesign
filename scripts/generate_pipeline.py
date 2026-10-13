"""Demo entry point: run the full design pipeline (C4 + Sequence) for one scenario.

Usage (from the repository root, with LM Studio running):
    uv run python scripts/generate_pipeline.py --scenario scenarios/social_network_chat.yaml
    uv run python scripts/generate_pipeline.py --scenario scenarios/social_network_chat.yaml --out-dir output/social
    uv run python scripts/generate_pipeline.py --scenario scenarios/social_network_chat.yaml --diagram-format svg
    uv run python scripts/generate_pipeline.py --scenario scenarios/social_network_chat.yaml --verbose

Connection settings come from .env / environment variables (see
.env.example); everything else comes from config.yaml. Exit codes:
0 - success, 1 - generation loop failed, 2 - configuration or LLM endpoint
failure.

--verbose switches logging to DEBUG: the agent then logs the raw LLM output
of every completion, which is the primary diagnostic artifact for parse
failures (truncation, preambles, code fences).

The pipeline executes in two stages:
1. C4 Architecture Generation: Generates the structural nodes and edges.
2. Sequence Diagram Generation: Uses the generated C4 nodes as technical
   lifelines to generate AST steps representing the dynamic interactions.

All resulting JSON graphs, ASTs, and PlantUML diagrams are saved to the
configured output directory.
"""

import argparse
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from application.results import (
    DesignGenerationResult,
    GenerationStatus,
    SequenceGenerationResult,
)
from application.services.sequence_generation_service import SequenceGenerationService
from application.usage import TokenUsage
from config.root import AppSettings, load_app_settings
from config.visualisation import VisualisationSettings
from domain.models import DesignScenario
from domain.models.sequence import InteractionScenario
from domain.specifications.sequence_validator import SequenceValidator
from infrastructure.agents.sequence_designer import SequenceDesignerAgent
from infrastructure.composition import build_design_generation_service
from infrastructure.exceptions.llm_exceptions import LlmConnectionError
from infrastructure.llm.client import LiteLlmClient
from infrastructure.prompts.fragments import render_scenario_summary
from infrastructure.visualisation.plantuml import (
    DiagramFileWriter,
    DiagramImageFormat,
    DiagramRenderingError,
    DiagramSavingError,
    DiagramService,
    resolve_image_renderer,
)
from infrastructure.visualisation.plantuml.sequence_builder import (
    SequenceDiagramBuilder,
)

_logger: logging.Logger = logging.getLogger("generate_pipeline")


def main() -> int:
    args: argparse.Namespace = _parse_args()
    _configure_logging(verbose=args.verbose)

    try:
        settings: AppSettings = load_app_settings()
    except (ValidationError, ValueError) as error:
        _logger.error("Settings are not configured: %s", error)
        _logger.error("Hint: create .env with ASD_BASE_URL / ASD_API_KEY.")
        return 2

    scenario: DesignScenario = _load_scenario(args.scenario)
    _log_header(settings, scenario)

    out_dir = (
        Path(args.out_dir) if args.out_dir else Path(settings.visualisation.diagram_dir)
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------
    # STAGE 1: C4 Architecture Generation
    # ---------------------------------------------------------
    _logger.info("=== STAGE 1: Generating C4 Architecture ===")
    c4_service = build_design_generation_service()

    start_time: float = time.perf_counter()
    try:
        c4_result: DesignGenerationResult = c4_service.generate(scenario)
    except LlmConnectionError as error:
        _logger.error("LLM endpoint failure in C4 stage: %s", error)
        return 2
    c4_wall_seconds: float = time.perf_counter() - start_time

    _log_attempts(c4_result.attempts, stage_name="C4")
    _log_summary(
        c4_result.status,
        c4_result.total_usage,
        len(c4_result.attempts),
        c4_wall_seconds,
        stage_name="C4",
    )

    if c4_result.graph is None or c4_result.status != GenerationStatus.SUCCEEDED:
        _logger.error("Stopping pipeline: C4 architecture generation failed.")
        return 1

    _save_json(
        c4_result.graph.model_dump_json(indent=2),
        out_dir / f"{scenario.identifier}_c4.json",
    )
    _render_c4_diagram(c4_result, scenario, settings.visualisation, args, out_dir)

    # ---------------------------------------------------------
    # STAGE 2: Sequence Diagram Generation
    # ---------------------------------------------------------
    _logger.info("=== STAGE 2: Generating Sequence Diagram ===")
    client = LiteLlmClient(settings=settings)
    seq_agent = SequenceDesignerAgent(client=client, settings=settings)
    seq_service = SequenceGenerationService(
        designer=seq_agent,
        validator=SequenceValidator(),
        max_attempts=settings.generation.max_attempts,
    )

    start_time = time.perf_counter()
    try:
        seq_result: SequenceGenerationResult = seq_service.generate(
            scenario, c4_result.graph
        )
    except LlmConnectionError as error:
        _logger.error("LLM endpoint failure in Sequence stage: %s", error)
        return 2
    seq_wall_seconds: float = time.perf_counter() - start_time

    _log_attempts(seq_result.attempts, stage_name="Sequence")
    _log_summary(
        seq_result.status,
        seq_result.total_usage,
        len(seq_result.attempts),
        seq_wall_seconds,
        stage_name="Sequence",
    )

    if (
        seq_result.system_design is None
        or seq_result.status != GenerationStatus.SUCCEEDED
    ):
        _logger.error("Sequence diagram generation failed.")
        return 1

    _save_json(
        seq_result.system_design.model_dump_json(indent=2),
        out_dir / f"{scenario.identifier}_sequence_ast.json",
    )

    # Render each interaction scenario into a separate image
    for idx, interaction in enumerate(
        seq_result.system_design.interaction_scenarios, start=1
    ):
        safe_req_id = re.sub(r"[^A-Za-z0-9_]", "_", interaction.scenario_id).lower()
        base_name = f"{scenario.identifier}_seq_{safe_req_id}"

        _logger.info(
            "Rendering sequence diagram %d/%d: %s",
            idx,
            len(seq_result.system_design.interaction_scenarios),
            interaction.requirement_name,
        )
        _render_sequence_diagram(
            interaction, base_name, settings.visualisation, args, out_dir
        )

    _logger.info("Pipeline completed successfully.")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the full design pipeline for one scenario."
    )
    parser.add_argument(
        "--scenario", type=str, required=True, help="Path to a scenario yaml file"
    )
    parser.add_argument(
        "--out-dir", type=str, default=None, help="Directory to save artifacts"
    )
    parser.add_argument(
        "--diagram-server",
        type=str,
        default=None,
        help="Diagram server (auto/plantuml/kroki)",
    )
    parser.add_argument(
        "--diagram-format",
        type=DiagramImageFormat,
        choices=[fmt.value for fmt in DiagramImageFormat],
        default=None,
    )
    parser.add_argument(
        "--no-diagram", action="store_true", help="Skip PlantUML image generation"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="DEBUG logging for raw LLM output"
    )
    return parser.parse_args()


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )


def _load_scenario(path: str) -> DesignScenario:
    scenario_path = Path(path)
    with scenario_path.open("r", encoding="utf-8") as stream:
        payload: Any = yaml.safe_load(stream)
    return DesignScenario.model_validate(payload)


def _log_header(settings: AppSettings, scenario: DesignScenario) -> None:
    _logger.info("=" * 64)
    _logger.info("AutoSystemDesign - Pipeline Run (C4 + Sequence)")
    _logger.info("=" * 64)
    _logger.info("Effective configuration")
    _logger.info("  model        : %s", settings.llm.model)
    _logger.info("  max_tokens   : %s", settings.llm.max_tokens)
    _logger.info("  max_attempts : %s", settings.generation.max_attempts)
    _logger.info("Scenario")
    for line in render_scenario_summary(scenario).splitlines():
        _logger.info("  %s", line)


def _log_attempts(attempts: list[Any], stage_name: str) -> None:
    _logger.info("%s Generation Attempts", stage_name)
    for attempt in attempts:
        parsed_mark = "parsed" if attempt.parsed else "UNPARSEABLE"
        if attempt.validation is None:
            validation_mark = "not run"
        elif attempt.validation.is_successful:
            validation_mark = "valid"
        else:
            validation_mark = f"{len(attempt.validation.errors)} error(s)"

        latency_mark = (
            f"{attempt.latency_seconds:.1f} s"
            if attempt.latency_seconds > 0.0
            else "n/a"
        )
        _logger.info(
            "  attempt %d: %s, validation: %s, tokens: %d, latency: %s",
            attempt.attempt_number,
            parsed_mark,
            validation_mark,
            attempt.usage.total_tokens,
            latency_mark,
        )

        if attempt.validation is not None:
            for error in attempt.validation.errors:
                _logger.info("      [%s] %s", error.error_code, error.message)
        for failure in attempt.parsing_failures:
            _logger.info(
                "      [%s] %s (at %s)",
                failure.error_type,
                failure.message,
                failure.location,
            )


def _log_summary(
    status: GenerationStatus,
    usage: TokenUsage,
    attempt_count: int,
    wall_seconds: float,
    stage_name: str,
) -> None:
    _logger.info(
        "%s Result: %s after %d attempt(s)", stage_name, status.value, attempt_count
    )
    _logger.info(
        "Tokens: prompt=%d, completion=%d, total=%d",
        usage.prompt_tokens,
        usage.completion_tokens,
        usage.total_tokens,
    )
    _logger.info("Wall time: %.1f s", wall_seconds)


def _save_json(payload: str, path: Path) -> None:
    path.write_text(payload + "\n", encoding="utf-8")
    _logger.info("Saved JSON artifact to: %s", path)


def _render_c4_diagram(
    result: DesignGenerationResult,
    scenario: DesignScenario,
    vis_settings: VisualisationSettings,
    args: argparse.Namespace,
    out_dir: Path,
) -> None:
    if args.no_diagram or result.graph is None:
        return

    server = args.diagram_server or vis_settings.server
    fmt = DiagramImageFormat(args.diagram_format or vis_settings.image_format)

    service = DiagramService(
        image_renderer=resolve_image_renderer(server), image_format=fmt
    )
    artifacts = service.generate(
        result.graph, title=f"C4 Container diagram for {scenario.identifier}"
    )

    try:
        image_bytes = service.render_image(artifacts)
        artifacts = artifacts.with_image(image_bytes)
    except DiagramRenderingError as error:
        _logger.warning("C4 Diagram image rendering failed: %s", error)

    try:
        written_paths = DiagramFileWriter().write(
            artifacts, out_dir, f"{scenario.identifier}_c4"
        )
        for path in written_paths:
            _logger.info("C4 Diagram artifact written: %s", path)
    except DiagramSavingError as error:
        _logger.warning("Saving C4 diagram artifacts failed: %s", error)


def _render_sequence_diagram(
    interaction: InteractionScenario,
    base_name: str,
    vis_settings: VisualisationSettings,
    args: argparse.Namespace,
    out_dir: Path,
) -> None:
    if args.no_diagram:
        return

    server = args.diagram_server or vis_settings.server
    fmt = DiagramImageFormat(args.diagram_format or vis_settings.image_format)

    service = DiagramService(
        source_builder=SequenceDiagramBuilder(),
        image_renderer=resolve_image_renderer(server),
        image_format=fmt,
    )

    artifacts = service.generate(interaction, title=interaction.requirement_name)

    try:
        image_bytes = service.render_image(artifacts)
        artifacts = artifacts.with_image(image_bytes)
    except DiagramRenderingError as error:
        _logger.warning(
            "Sequence Diagram image rendering failed for %s: %s", base_name, error
        )

    try:
        written_paths = DiagramFileWriter().write(artifacts, out_dir, base_name)
        for path in written_paths:
            _logger.info("Sequence Diagram artifact written: %s", path)
    except DiagramSavingError as error:
        _logger.warning(
            "Saving Sequence diagram artifacts failed for %s: %s", base_name, error
        )


if __name__ == "__main__":
    sys.exit(main())
