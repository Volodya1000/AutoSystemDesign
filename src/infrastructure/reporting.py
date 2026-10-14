"""Logging utilities and port adapters.

This module implements the application-level reporting ports. It is the
only place where application-level reporting meets the ``logging`` module.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from application.pipeline.outcome import StageOutcome, StageStatus
from application.results import GenerationAttempt
from application.usage import TokenUsage
from config.root import AppSettings
from domain.models import DesignScenario
from infrastructure.prompts.fragments import render_scenario_summary

_logger = logging.getLogger("pipeline.report")


# --- existing helpers -------------------------------------------------------


def log_header(settings: AppSettings, scenario: DesignScenario) -> None:
    """Logs the effective configuration and the scenario summary."""
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


def log_attempts(attempts: Sequence[GenerationAttempt], label: str) -> None:
    """Logs per-attempt outcomes of a repair loop."""
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
    """Logs token accounting and generation wall time for one call."""
    _logger.info(
        "Tokens: prompt=%d, completion=%d, total=%d",
        usage.prompt_tokens,
        usage.completion_tokens,
        usage.total_tokens,
    )
    _logger.info("Generation time: %.1f s", generation_seconds)


# --- port adapters ----------------------------------------------------------


class LoggingGenerationReporter:
    """Adapter: GenerationReporter port -> existing logging helpers."""

    def attempts(self, attempts: Sequence[GenerationAttempt], label: str) -> None:
        log_attempts(attempts, label)

    def tokens(self, usage: TokenUsage, generation_seconds: float) -> None:
        log_token_totals(usage, generation_seconds)


class LoggingPipelineReporter:
    """Adapter: PipelineReporter port -> aggregated INFO summary."""

    def report(self, outcomes: Sequence[StageOutcome[object]]) -> None:
        overall: StageStatus = self._overall_status(outcomes)
        _logger.info("=" * 64)
        _logger.info("Pipeline summary")
        _logger.info("  status : %s", overall.value)

        total_seconds: float = 0.0
        total_tokens: int = 0
        total_artifacts: int = 0

        for outcome in outcomes:
            total_seconds += outcome.duration_seconds
            total_tokens += outcome.total_tokens
            total_artifacts += len(outcome.artifacts)
            _logger.info(
                "  stage %-10s : %-9s  %.1f s  %d tok  %d artifacts%s",
                outcome.name,
                outcome.status.value,
                outcome.duration_seconds,
                outcome.total_tokens,
                len(outcome.artifacts),
                f"  ({outcome.message})" if outcome.message else "",
            )
            for warning in outcome.warnings:
                _logger.warning("    [%s] %s", outcome.name, warning)

        _logger.info(
            "  total              : %.1f s  %d tok  %d artifacts",
            total_seconds,
            total_tokens,
            total_artifacts,
        )
        _logger.info("=" * 64)

    @staticmethod
    def _overall_status(
        outcomes: Sequence[StageOutcome[object]],
    ) -> StageStatus:
        if any(o.status is StageStatus.FAILED for o in outcomes):
            return StageStatus.FAILED
        if any(o.status is StageStatus.PARTIAL for o in outcomes):
            return StageStatus.PARTIAL
        return StageStatus.SUCCEEDED
