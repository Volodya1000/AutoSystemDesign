"""Demo entry point: run the full design generation loop for one scenario.

Usage (from the repository root, with LM Studio running):
    uv run python scripts/generate_design.py
    uv run python scripts/generate_design.py --scenario scenarios/ecommerce_checkout.yaml
    uv run python scripts/generate_design.py --out output/graph.json
    uv run python scripts/generate_design.py --diagram-format png
    uv run python scripts/generate_design.py --diagram-server kroki
    uv run python scripts/generate_design.py --diagram-server http://localhost:8080
    uv run python scripts/generate_design.py --no-diagram
    uv run python scripts/generate_design.py --verbose

Connection settings come from .env / environment variables (see
.env.example); everything else comes from config.yaml. Exit codes:
0 - success, 1 - generation loop failed, 2 - configuration or LLM endpoint
failure.

--verbose switches logging to DEBUG: the agent then logs the raw LLM output
of every completion, which is the primary diagnostic artifact for parse
failures (truncation, preambles, code fences).

When a run produces a parsable graph, the final topology is also rendered
as a PlantUML C4 Container diagram (see infrastructure.visualisation.plantuml):
the .puml source is always saved, and the image is fetched best-effort
from the diagram server configured in config.yaml (visualisation.server:
"auto" - public PlantUML server with the public Kroki gateway as an
automatic fallback; "plantuml"; "kroki"; or a self-hosted plantuml-server
URL, see deploy/plantuml). CLI flags override the config. Rendering or
saving failures only downgrade the log to warnings and never change the
exit code; use --no-diagram to skip diagram generation entirely.
"""

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from application.results import (
    DesignGenerationResult,
    GenerationAttempt,
    GenerationStatus,
)
from application.usage import TokenUsage
from config.root import AppSettings, load_app_settings
from config.visualisation import VisualisationSettings
from domain.models import (
    ArchitectureGraph,
    BudgetRequirement,
    DesignScenario,
    LatencyRequirement,
    WorkloadProfile,
)
from infrastructure.composition import build_design_generation_service
from infrastructure.exceptions.llm_exceptions import LlmConnectionError
from infrastructure.prompts.fragments import render_scenario_summary
from infrastructure.visualisation.plantuml import (
    DiagramArtifacts,
    DiagramFileWriter,
    DiagramImageFormat,
    DiagramRenderingError,
    DiagramSavingError,
    DiagramService,
    resolve_image_renderer,
)

_logger: logging.Logger = logging.getLogger("generate_design")

_DEFAULT_SCENARIO: DesignScenario = DesignScenario(
    identifier="ecommerce_checkout",
    description="Checkout flow for a mid-size e-commerce platform",
    workload=WorkloadProfile(
        baseline_requests_per_second=120.0,
        peak_requests_per_second=400.0,
        read_ratio=0.7,
    ),
    requirements=[
        LatencyRequirement(threshold_value=300.0, percentile=99.0),
        BudgetRequirement(threshold_value=3000.0),
    ],
)


def main() -> int:
    """Runs the generation loop and logs a full report; returns exit code."""
    args: argparse.Namespace = _parse_args()
    _configure_logging(verbose=args.verbose)

    try:
        settings: AppSettings = load_app_settings()
    except (ValidationError, ValueError) as error:
        _logger.error("Settings are not configured: %s", error)
        _logger.error(
            "Hint: create .env with ASD_BASE_URL / ASD_API_KEY (see .env.example)."
        )
        return 2

    scenario: DesignScenario = _load_scenario(args.scenario)

    _log_header(settings, scenario)
    _logger.info("Running the generation loop (live LLM logs follow)...")

    service = build_design_generation_service()
    start_time: float = time.perf_counter()
    try:
        result: DesignGenerationResult = service.generate(scenario)
    except LlmConnectionError as error:
        _logger.error("LLM endpoint failure: %s", error)
        return 2
    wall_seconds: float = time.perf_counter() - start_time

    _log_attempts(result)
    _log_summary(result, wall_seconds)
    _log_graph(result)
    if args.out is not None:
        _save_graph(result, args.out)
    _render_diagram(result, scenario, settings.visualisation, args)
    return 0 if result.status is GenerationStatus.SUCCEEDED else 1


def _parse_args() -> argparse.Namespace:
    """Parses command line arguments."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Run the LLM architecture design loop for one scenario."
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        help="Path to a scenario yaml file (default: built-in demo scenario)",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Path to save the final ArchitectureGraph as JSON",
    )
    parser.add_argument(
        "--diagram-server",
        type=str,
        default=None,
        help=(
            "Diagram server: auto, plantuml, kroki or a plantuml-server URL "
            "(default: visualisation.server from config.yaml)"
        ),
    )
    parser.add_argument(
        "--diagram-format",
        type=DiagramImageFormat,
        choices=[fmt.value for fmt in DiagramImageFormat],
        default=None,
        help="Image format of the C4 diagram (default: config visualisation)",
    )
    parser.add_argument(
        "--diagram-dir",
        type=str,
        default=None,
        help="Directory for diagram artifacts (default: config visualisation)",
    )
    parser.add_argument(
        "--no-diagram",
        action="store_true",
        help="Skip PlantUML C4 diagram generation",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="DEBUG logging: shows the raw LLM output of every completion",
    )
    return parser.parse_args()


def _configure_logging(verbose: bool) -> None:
    """Configures root logging: INFO by default, DEBUG with --verbose."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )


def _load_scenario(path: str | None) -> DesignScenario:
    """Returns the built-in demo scenario or one loaded from a yaml file."""
    if path is None:
        return _DEFAULT_SCENARIO
    scenario_path: Path = Path(path)
    with scenario_path.open("r", encoding="utf-8") as stream:
        payload: Any = yaml.safe_load(stream)
    return DesignScenario.model_validate(payload)


def _log_header(settings: AppSettings, scenario: DesignScenario) -> None:
    """Logs the effective configuration and the scenario."""
    _logger.info("=" * 64)
    _logger.info("AutoSystemDesign - architecture generation run")
    _logger.info("=" * 64)
    _logger.info("Effective configuration")
    _logger.info("  model        : %s", settings.llm.model)
    _logger.info("  base_url     : %s", settings.base_url)
    _logger.info("  temperature  : %s", settings.llm.temperature)
    _logger.info("  max_tokens   : %s", settings.llm.max_tokens)
    _logger.info("  timeout      : %s s", settings.llm.timeout_seconds)
    _logger.info("  output mode  : %s", settings.llm.structured_output_mode.value)
    _logger.info("  max_attempts : %s", settings.generation.max_attempts)
    _logger.info("  diagram srv  : %s", settings.visualisation.server)
    _logger.info("Scenario")
    for line in render_scenario_summary(scenario).splitlines():
        _logger.info("  %s", line)


def _log_attempts(result: DesignGenerationResult) -> None:
    """Logs per-attempt outcomes of the repair loop."""
    _logger.info("Generation attempts")
    attempt: GenerationAttempt
    for attempt in result.attempts:
        parsed_mark: str = "parsed" if attempt.parsed else "UNPARSEABLE"
        if attempt.validation is None:
            validation_mark: str = "not run"
        elif attempt.validation.is_successful:
            validation_mark = "valid"
        else:
            validation_mark = f"{len(attempt.validation.errors)} error(s)"
        latency_mark: str = (
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


def _log_summary(result: DesignGenerationResult, wall_seconds: float) -> None:
    """Logs the final status and token accounting."""
    total_usage: TokenUsage = result.total_usage
    _logger.info(
        "Result: %s after %d attempt(s)", result.status.value, len(result.attempts)
    )
    _logger.info(
        "Tokens: prompt=%d, completion=%d, total=%d",
        total_usage.prompt_tokens,
        total_usage.completion_tokens,
        total_usage.total_tokens,
    )
    _logger.info("Wall time: %.1f s", wall_seconds)


def _log_graph(result: DesignGenerationResult) -> None:
    """Logs the final architecture graph in a human-readable form."""
    graph = result.graph
    if graph is None:
        _logger.info("Graph: none (no attempt produced a parsable graph)")
        return
    _logger.info("Final graph: %d nodes, %d edges", len(graph.nodes), len(graph.edges))
    _logger.info("Nodes:")
    for node in graph.nodes:
        fields: dict[str, Any] = node.model_dump(exclude={"identifier", "node_type"})
        rendered_fields: str = " ".join(
            f"{key}={value}" for key, value in fields.items()
        )
        _logger.info(
            "  [%s] %s %s", node.node_type.value, node.identifier, rendered_fields
        )
    _logger.info("Edges:")
    for edge in graph.edges:
        async_marker: str = " (async)" if edge.protocol.is_asynchronous else ""
        _logger.info(
            "  %s --%s%s--> %s (network: %s ms)",
            edge.source_identifier,
            edge.protocol.name,
            async_marker,
            edge.target_identifier,
            edge.network_latency_milliseconds,
        )
    monthly_cost: float = 0.0
    for node in graph.nodes:
        node_cost: Any = getattr(node, "monthly_cost_usd", None)
        if isinstance(node_cost, (int, float)):
            monthly_cost += float(node_cost)
    _logger.info("Total monthly cost of capacity nodes: $%.2f", monthly_cost)
    _logger.info("(use --out <path> to save the full graph as JSON)")


def _save_graph(result: DesignGenerationResult, output_path: str) -> None:
    """Saves the final graph as JSON; skips when nothing was parsed."""
    graph = result.graph
    if graph is None:
        _logger.info("Nothing to save: no parsed graph.")
        return
    path: Path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(graph.model_dump_json(indent=2) + "\n", encoding="utf-8")
    _logger.info("Graph JSON saved to: %s", path)


def _render_diagram(
    result: DesignGenerationResult,
    scenario: DesignScenario,
    visualisation: VisualisationSettings,
    args: argparse.Namespace,
) -> None:
    """Renders the final graph as a PlantUML C4 Container diagram.

    Even a graph that failed validation is rendered: the diagram doubles
    as a diagnostic artifact for repair analysis. All diagram steps are
    best-effort presentation and never change the run's exit code.
    """
    if args.no_diagram:
        _logger.info("Diagram: skipped (--no-diagram)")
        return
    graph: ArchitectureGraph | None = result.graph
    if graph is None:
        _logger.info("Diagram: skipped (no attempt produced a parsable graph)")
        return
    server, image_format, diagram_dir = _resolve_diagram_settings(visualisation, args)
    artifacts: DiagramArtifacts = _generate_diagram(
        graph, scenario, server, image_format
    )
    _save_diagram(artifacts, scenario, diagram_dir)


def _resolve_diagram_settings(
    visualisation: VisualisationSettings,
    args: argparse.Namespace,
) -> tuple[str, DiagramImageFormat, str]:
    """Merges the CLI flags over the yaml config for diagram rendering."""
    server: str = args.diagram_server or visualisation.server
    image_format: DiagramImageFormat = DiagramImageFormat(
        args.diagram_format or visualisation.image_format
    )
    diagram_dir: str = args.diagram_dir or visualisation.diagram_dir
    return server, image_format, diagram_dir


def _generate_diagram(
    graph: ArchitectureGraph,
    scenario: DesignScenario,
    server: str,
    image_format: DiagramImageFormat,
) -> DiagramArtifacts:
    """Builds the diagram source and fetches the image best-effort."""
    service = DiagramService(
        image_renderer=resolve_image_renderer(server),
        image_format=image_format,
    )
    artifacts: DiagramArtifacts = service.generate(
        graph, title=f"Container diagram for {scenario.identifier}"
    )
    try:
        rendered_image: bytes = service.render_image(artifacts)
    except DiagramRenderingError as error:
        _logger.warning("Diagram image rendering failed: %s", error)
        _logger.warning(
            "The .puml source is still saved; open the diagram URL below in a "
            "browser or render the source with any local PlantUML tool."
        )
    else:
        artifacts = artifacts.with_image(rendered_image)
    return artifacts


def _save_diagram(
    artifacts: DiagramArtifacts,
    scenario: DesignScenario,
    diagram_dir: str,
) -> None:
    """Writes the diagram artifacts into the diagram directory."""
    try:
        written_paths: list[Path] = DiagramFileWriter().write(
            artifacts, Path(diagram_dir), scenario.identifier
        )
    except DiagramSavingError as error:
        _logger.warning("Saving diagram artifacts failed: %s", error)
        return
    path: Path
    for path in written_paths:
        _logger.info("Diagram artifact written: %s", path)
    _logger.info("Diagram image URL (rendered on demand): %s", artifacts.image_url)


if __name__ == "__main__":
    sys.exit(main())
