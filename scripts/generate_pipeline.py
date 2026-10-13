"""Pipeline runner: C4 Architecture -> Sequence Diagrams (N+1)."""

import argparse
import logging
import re
import sys
import time
from pathlib import Path

import yaml
from pydantic import ValidationError

from application.results import GenerationStatus
from config.root import load_app_settings
from domain.models import DesignScenario
from domain.models.sequence import InteractionScenario
from domain.models.topology import ArchitectureGraph
from infrastructure.composition import (
    build_design_generation_service,
    build_sequence_generation_service,
)
from infrastructure.exceptions.llm_exceptions import LlmConnectionError
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


def main() -> int:
    args = _parse_args()
    _configure_logging(args.verbose)

    try:
        load_app_settings()
    except (ValidationError, ValueError) as error:
        _logger.error("Settings error: %s", error)
        return 2

    scenario: DesignScenario = _load_scenario(args.scenario)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    _logger.info("=== STAGE 1: Generating C4 Architecture ===")
    c4_graph: ArchitectureGraph | int = _run_c4_stage(scenario, out_dir, args)
    if isinstance(c4_graph, int):
        return c4_graph

    _logger.info("=== STAGE 2: Generating Sequence Diagrams ===")
    return _run_sequence_stage(scenario, c4_graph, out_dir, args)


def _run_c4_stage(
    scenario: DesignScenario,
    out_dir: Path,
    args: argparse.Namespace,
) -> ArchitectureGraph | int:
    """Runs stage 1; returns the graph or a process exit code on failure."""
    c4_service = build_design_generation_service()
    start_time = time.perf_counter()
    try:
        c4_result = c4_service.generate(scenario)
    except LlmConnectionError as e:
        _logger.error("C4 LLM Error: %s", e)
        return 2

    c4_time = time.perf_counter() - start_time
    _logger.info("C4 Result: %s in %.1f s", c4_result.status.value, c4_time)

    if c4_result.status != GenerationStatus.SUCCEEDED or c4_result.graph is None:
        _logger.error("C4 Architecture failed. Aborting pipeline.")
        return 1

    (out_dir / f"{scenario.identifier}_c4.json").write_text(
        c4_result.graph.model_dump_json(indent=2), encoding="utf-8"
    )
    _render_c4_diagram(c4_result.graph, scenario.identifier, args, out_dir)
    return c4_result.graph


def _run_sequence_stage(
    scenario: DesignScenario,
    graph: ArchitectureGraph,
    out_dir: Path,
    args: argparse.Namespace,
) -> int:
    seq_service = build_sequence_generation_service()
    start_time = time.perf_counter()
    try:
        seq_result = seq_service.generate(scenario, graph)
    except LlmConnectionError as e:
        _logger.error("Sequence LLM Error: %s", e)
        return 2

    seq_time = time.perf_counter() - start_time
    _logger.info("Sequence Generation finished in %.1f s", seq_time)

    if seq_result.roles_catalog:
        (out_dir / f"{scenario.identifier}_roles.json").write_text(
            seq_result.roles_catalog.model_dump_json(indent=2), encoding="utf-8"
        )

    for req_id, req_result in seq_result.scenarios_results.items():
        if req_result.interaction_scenario:
            safe_id = re.sub(r"[^A-Za-z0-9_]", "_", req_id).lower()
            base_name = f"{scenario.identifier}_seq_{safe_id}"
            _render_sequence_diagram(
                req_result.interaction_scenario, base_name, args, out_dir
            )
        else:
            _logger.warning(
                "Failed to generate sequence diagram for requirement: %s", req_id
            )

    return 0 if seq_result.is_successful else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full design pipeline.")
    parser.add_argument(
        "--scenario", type=str, required=True, help="Path to scenario YAML"
    )
    parser.add_argument(
        "--out-dir", type=str, default="output", help="Directory for output files"
    )
    parser.add_argument(
        "--diagram-server",
        type=str,
        default="auto",
        help="Diagram server (auto/plantuml/kroki)",
    )
    parser.add_argument(
        "--diagram-format", type=DiagramImageFormat, default=DiagramImageFormat.PNG
    )
    parser.add_argument(
        "--no-diagram", action="store_true", help="Skip diagram rendering"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    return parser.parse_args()


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
    out_dir: Path,
) -> None:
    if args.no_diagram:
        return
    service = DiagramService(
        image_renderer=resolve_image_renderer(args.diagram_server),
        image_format=args.diagram_format,
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
    out_dir: Path,
) -> None:
    if args.no_diagram:
        return
    service = DiagramService(
        source_builder=SequenceDiagramBuilder(),
        image_renderer=resolve_image_renderer(args.diagram_server),
        image_format=args.diagram_format,
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
