"""Demo entry point: run the full design generation loop for one scenario.

Usage (from the repository root, with LM Studio running):
    uv run python scripts/generate_design.py
    uv run python scripts/generate_design.py --scenario scenarios/ecommerce_checkout.yaml
    uv run python scripts/generate_design.py --out output/graph.json
    uv run python scripts/generate_design.py --verbose

Connection settings come from .env / environment variables (see
.env.example); everything else comes from config.yaml. Exit codes:
0 - success, 1 - generation loop failed, 2 - configuration or LLM endpoint
failure.

--verbose switches logging to DEBUG: the agent then logs the raw LLM output
of every completion, which is the primary diagnostic artifact for parse
failures (truncation, preambles, code fences).
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
from domain.models import (
    BudgetRequirement,
    DesignScenario,
    LatencyRequirement,
    WorkloadProfile,
)
from infrastructure.composition import build_design_generation_service
from infrastructure.exceptions.llm_exceptions import LlmConnectionError
from infrastructure.prompts.fragments import render_scenario_summary

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


if __name__ == "__main__":
    sys.exit(main())
