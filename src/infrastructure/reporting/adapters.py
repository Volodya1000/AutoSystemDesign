"""Port adapters: application-level reporting ports -> logging helpers.

This module is the single place where application-layer reporting ports
(``GenerationReporterProtocol``, ``PipelineReporterProtocol``) meet the ``logging``
module. It delegates formatting to ``helpers`` so the adapters stay thin.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from application.pipeline.result import PipelineRunResult
from infrastructure.reporting.helpers import log_attempts, log_token_totals

if TYPE_CHECKING:
    from collections.abc import Sequence

    from application.pipeline.outcome import StageOutcome, StageStatus
    from application.results import GenerationAttempt
    from application.usage import TokenUsage

_logger = logging.getLogger("pipeline.report")


class LoggingGenerationReporter:
    """Adapter: GenerationReporterProtocol port -> logging helpers."""

    def attempts[PayloadT](
        self, attempts: Sequence[GenerationAttempt[PayloadT]], label: str
    ) -> None:
        log_attempts(attempts, label)

    def tokens(self, usage: TokenUsage, generation_seconds: float) -> None:
        log_token_totals(usage, generation_seconds)


class LoggingPipelineReporter:
    """Adapter: PipelineReporterProtocol port -> aggregated INFO summary."""

    def report(self, outcomes: Sequence[StageOutcome[object]]) -> None:
        overall: StageStatus = PipelineRunResult(tuple(outcomes)).status
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
