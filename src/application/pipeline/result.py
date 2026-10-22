"""Structured pipeline result, independent of process exit codes."""

from __future__ import annotations

from dataclasses import dataclass

from application.pipeline.outcome import StageOutcome, StageStatus


@dataclass(frozen=True, slots=True)
class PipelineRunResult:
    """Ordered stage outcomes with derived summary, not duplicated state.

    The result container is immutable; nested payloads are not deep-copied.
    """

    outcomes: tuple[StageOutcome[object], ...]

    @property
    def status(self) -> StageStatus:
        """Compute FAILED, PARTIAL, or SUCCEEDED from stage outcomes."""
        if self.failed_stage is not None:
            return StageStatus.FAILED
        if any(outcome.status is StageStatus.PARTIAL for outcome in self.outcomes):
            return StageStatus.PARTIAL
        return StageStatus.SUCCEEDED

    @property
    def failed_stage(self) -> StageOutcome[object] | None:
        """Find the first failed stage outcome, if any."""
        return next(
            (
                outcome
                for outcome in self.outcomes
                if outcome.status is StageStatus.FAILED
            ),
            None,
        )
