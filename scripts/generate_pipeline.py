"""Pipeline runner: C4 Architecture -> Sequence Diagrams (N+1).

Usage (from the repository root, with LM Studio running):
    uv run scripts/generate_pipeline.py --scenario scenarios/ecommerce_checkout.yaml
    uv run scripts/generate_pipeline.py --scenario scenarios/x.yaml --out-dir output
    uv run scripts/generate_pipeline.py --scenario scenarios/x.yaml --diagram-server kroki
    uv run scripts/generate_pipeline.py --scenario scenarios/x.yaml --no-diagram
    uv run scripts/generate_pipeline.py --scenario scenarios/x.yaml --verbose

CLI flags override visualisation settings from config.yaml; when a flag is
omitted, the value from config.yaml is used. Exit codes: 0 - success,
1 - generation failed or partially failed, 2 - configuration or LLM endpoint
failure.

Artifacts written to --out-dir: <scenario>_c4.json, <scenario>_roles.json,
<scenario>_seq_<req>_ast.json, plus the rendered PlantUML diagrams.
"""

import argparse
import logging
import re
import sys
import time
from pathlib import Path

import yaml
from pydantic import ValidationError

from application.results import GenerationStatus, SequenceGenerationResult
from config.root import AppSettings, load_app_settings
from domain.models import DesignScenario
from domain.models.sequence import InteractionScenario
from domain.models.topology import ArchitectureGraph
from infrastructure.composition import (
    build_design_generation_service,
    build_sequence_generation_service,
)
from infrastructure.exceptions.llm_exceptions import LlmConnectionError
from infrastructure.reporting import log_attempts, log_header, log_token_totals
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

_logger: logging.Logger = logging.getLogger("pipeline")


class PipelineStageError(Exception):
    """Raised when a pipeline stage cannot produce its artifact."""

    def __init__(self, exit_code: int, message: str) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def main() -> int:
    args = _parse_args()
    _configure_logging(args.verbose)

    try:
        settings: AppSettings = load_app_settings()
    except (ValidationError, ValueError) as error:
        _logger.error("Settings error: %s", error)
        return 2

    scenario: DesignScenario = _load_scenario(args.scenario)
    out_dir, server, image_format = _resolve_visualisation(args, settings)
    out_dir.mkdir(parents=True, exist_ok=True)

    log_header(settings, scenario)

    try:
        _logger.info("=== STAGE 1: Generating C4 Architecture ===")
        c4_graph: ArchitectureGraph = _run_c4_stage(
            scenario, out_dir, args, server, image_format
        )

        _logger.info("=== STAGE 2: Generating Sequence Diagrams ===")
        seq_successful: bool = _run_sequence_stage(
            scenario, c4_graph, out_dir, args, server, image_format
        )
    except PipelineStageError as error:
        _logger.error("%s", error)
        return error.exit_code
    except LlmConnectionError as error:
        _logger.error("LLM endpoint failure: %s", error)
        return 2

    return 0 if seq_successful else 1


def _run_c4_stage(
    scenario: DesignScenario,
    out_dir: Path,
    args: argparse.Namespace,
    server: str,
    image_format: DiagramImageFormat,
) -> ArchitectureGraph:
    """Runs stage 1; returns the validated graph or raises PipelineStageError."""
    c4_service = build_design_generation_service()
    start_time = time.perf_counter()
    c4_result = c4_service.generate(scenario)
    c4_time = time.perf_counter() - start_time

    log_attempts(c4_result.attempts, "C4 generation attempts")
    _logger.info("C4 Result: %s in %.1f s", c4_result.status.value, c4_time)
    log_token_totals(c4_result.total_usage, c4_time)

    if c4_result.status is not GenerationStatus.SUCCEEDED or c4_result.graph is None:
        raise PipelineStageError(1, "C4 Architecture failed. Aborting pipeline.")

    (out_dir / f"{scenario.identifier}_c4.json").write_text(
        c4_result.graph.model_dump_json(indent=2), encoding="utf-8"
    )
    _render_c4_diagram(
        c4_result.graph, scenario.identifier, args, server, image_format, out_dir
    )
    return c4_result.graph


def _run_sequence_stage(
    scenario: DesignScenario,
    graph: ArchitectureGraph,
    out_dir: Path,
    args: argparse.Namespace,
    server: str,
    image_format: DiagramImageFormat,
) -> bool:
    """Runs stage 2; returns True when every requirement succeeded."""
    seq_service = build_sequence_generation_service()
    start_time = time.perf_counter()
    seq_result: SequenceGenerationResult = seq_service.generate(scenario, graph)
    seq_time = time.perf_counter() - start_time

    _logger.info("Sequence Generation finished in %.1f s", seq_time)
    log_attempts(seq_result.roles_attempts, "Roles catalog attempts")
    log_token_totals(seq_result.total_usage, seq_time)

    if seq_result.roles_catalog is not None:
        (out_dir / f"{scenario.identifier}_roles.json").write_text(
            seq_result.roles_catalog.model_dump_json(indent=2),
            encoding="utf-8",
        )

    for req_id, req_result in seq_result.scenarios_results.items():
        safe_id: str = re.sub(r"[^A-Za-z0-9_]", "_", req_id).lower()
        base_name: str = f"{scenario.identifier}_seq_{safe_id}"
        log_attempts(req_result.attempts, f"Interaction attempts for {req_id}")

        interaction: InteractionScenario | None = req_result.interaction_scenario
        if interaction is None:
            _logger.warning(
                "Failed to generate sequence diagram for requirement: %s", req_id
            )
            continue

        (out_dir / f"{base_name}_ast.json").write_text(
            interaction.model_dump_json(indent=2), encoding="utf-8"
        )
        _render_sequence_diagram(
            interaction, base_name, args, server, image_format, out_dir
        )

    return seq_result.is_successful


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
            "Override visualisation.server (auto/plantuml/kroki or a "
            "plantuml-server URL)"
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


def _resolve_visualisation(
    args: argparse.Namespace,
    settings: AppSettings,
) -> tuple[Path, str, DiagramImageFormat]:
    """Merges CLI flags over visualisation settings from config.yaml."""
    visualisation = settings.visualisation
    out_dir: Path = Path(args.out_dir or visualisation.diagram_dir)
    server: str = args.diagram_server or visualisation.server
    image_format: DiagramImageFormat = DiagramImageFormat(
        args.diagram_format or visualisation.image_format
    )
    return out_dir, server, image_format


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    if verbose:
        logging.getLogger("LiteLLM").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)


def _load_scenario(path: str) -> DesignScenario:
    with Path(path).open("r", encoding="utf-8") as f:
        return DesignScenario.model_validate(yaml.safe_load(f))


def _render_c4_diagram(
    graph: ArchitectureGraph,
    identifier: str,
    args: argparse.Namespace,
    server: str,
    image_format: DiagramImageFormat,
    out_dir: Path,
) -> None:
    if args.no_diagram:
        return
    service = DiagramService(
        image_renderer=resolve_image_renderer(server),
        image_format=image_format,
    )
    artifacts = service.generate(graph, title=f"C4 Container: {identifier}")
    try:
        image_bytes = service.render_image(artifacts)
        artifacts = artifacts.with_image(image_bytes)
    except DiagramRenderingError as error:
        _logger.warning("C4 rendering failed: %s", error)

    try:
        written = DiagramFileWriter().write(artifacts, out_dir, f"{identifier}_c4")
        for p in written:
            _logger.info("C4 artifact written: %s", p)
    except DiagramSavingError as error:
        _logger.warning("Saving C4 diagram failed: %s", error)


def _render_sequence_diagram(
    interaction: InteractionScenario,
    base_name: str,
    args: argparse.Namespace,
    server: str,
    image_format: DiagramImageFormat,
    out_dir: Path,
) -> None:
    if args.no_diagram:
        return
    service = DiagramService(
        source_builder=SequenceDiagramBuilder(),
        image_renderer=resolve_image_renderer(server),
        image_format=image_format,
    )
    artifacts = service.generate(interaction, title=interaction.description)
    try:
        image_bytes = service.render_image(artifacts)
        artifacts = artifacts.with_image(image_bytes)
    except DiagramRenderingError as error:
        _logger.warning("Sequence rendering failed for %s: %s", base_name, error)

    try:
        written = DiagramFileWriter().write(artifacts, out_dir, base_name)
        for p in written:
            _logger.info("Sequence artifact written: %s", p)
    except DiagramSavingError as error:
        _logger.warning("Saving Sequence diagram failed for %s: %s", base_name, error)


if __name__ == "__main__":
    sys.exit(main())
