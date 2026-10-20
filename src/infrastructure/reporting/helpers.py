"""Pure logging helpers shared by reporters and the CLI entry point.

These functions know how to format the domain into log lines. They have
no dependency on the application ports and can be called directly from
scripts or notebooks without constructing an adapter.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from application.formatting.scenario_summary import render_scenario_summary

if TYPE_CHECKING:
    from collections.abc import Sequence

    from application.results import GenerationAttempt
    from application.usage import TokenUsage
    from config.root import AppSettings
    from domain.models import DesignScenario

_logger = logging.getLogger("pipeline.report")


def log_header(settings: AppSettings, scenario: DesignScenario) -> None:
    """Log the effective configuration and the scenario summary."""
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
    _logger.info("  seq parallel : %s", settings.generation.sequence_parallelism)
    _logger.info("  diagram srv  : %s", settings.visualisation.server)
    _logger.info("Scenario")
    for line in render_scenario_summary(scenario).splitlines():
        _logger.info("  %s", line)


def log_attempts(attempts: Sequence[GenerationAttempt], label: str) -> None:
    """Log per-attempt outcomes of a repair loop."""
    _logger.info(label)
    for attempt in attempts:
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


def log_token_totals(usage: TokenUsage, generation_seconds: float) -> None:
    """Log token accounting and generation wall time for one call."""
    _logger.info(
        "Tokens: prompt=%d, completion=%d, total=%d",
        usage.prompt_tokens,
        usage.completion_tokens,
        usage.total_tokens,
    )
    _logger.info("Generation time: %.1f s", generation_seconds)
