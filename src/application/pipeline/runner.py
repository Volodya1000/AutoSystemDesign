"""Ordered execution of stages; process exit codes belong to CLI callers."""

from __future__ import annotations

import logging
from types import MappingProxyType
from typing import TYPE_CHECKING

from application.pipeline.context import StageContext
from application.pipeline.outcome import StageOutcome, StageStatus
from application.pipeline.result import PipelineRunResult

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from application.pipeline.protocols import (
        ArtifactWriterProtocol,
        PipelineReporterProtocol,
    )
    from application.pipeline.stage import PipelineStageProtocol, StageId
    from domain.models import DesignScenario

_logger = logging.getLogger("pipeline.runner")


class PipelineConfigurationError(ValueError):
    """Invalid stage configuration for the pipeline runner."""

    @classmethod
    def no_stages(cls) -> PipelineConfigurationError:
        return cls("PipelineRunner requires at least one stage")

    @classmethod
    def duplicate_stage_id(cls, stage_id: StageId) -> PipelineConfigurationError:
        return cls(
            f"Duplicate stage name '{stage_id}'; stage names must "
            "be unique because outcomes are keyed by name"
        )

    @classmethod
    def dependency_not_scheduled(
        cls, stage_id: StageId, dependency: StageId
    ) -> PipelineConfigurationError:
        return cls(
            f"Stage '{stage_id}' depends on '{dependency}', "
            "which is not scheduled before it"
        )


class PipelineRunner:
    def __init__(
        self,
        stages: Sequence[PipelineStageProtocol],
        reporter: PipelineReporterProtocol,
    ) -> None:
        stages_tuple: tuple[PipelineStageProtocol, ...] = tuple(stages)
        if not stages_tuple:
            raise PipelineConfigurationError.no_stages()
        self._validate_stages(stages_tuple)
        self._stages: tuple[PipelineStageProtocol, ...] = stages_tuple
        self._reporter: PipelineReporterProtocol = reporter

    def run(
        self,
        scenario: DesignScenario,
        out_dir: Path,
        writer: ArtifactWriterProtocol,
    ) -> PipelineRunResult:
        upstream: dict[StageId, StageOutcome[object]] = {}
        outcomes: list[StageOutcome[object]] = []

        for stage in self._stages:
            _logger.info("=== STAGE: %s ===", stage.name)
            context = StageContext(
                scenario=scenario,
                out_dir=out_dir,
                writer=writer,
                upstream=MappingProxyType(dict(upstream)),
            )
            outcome: StageOutcome[object] = stage.run(context)
            outcomes.append(outcome)
            upstream[stage.name] = outcome

            if outcome.status is StageStatus.FAILED:
                break

        result: PipelineRunResult = PipelineRunResult(outcomes=tuple(outcomes))
        self._reporter.report(result.outcomes)
        return result

    @staticmethod
    def _validate_stages(stages: tuple[PipelineStageProtocol, ...]) -> None:
        """Validate stage-name uniqueness and dependency ordering.

        Results are keyed by stage name in ``upstream``, so duplicate names
        would silently overwrite each other; dependencies must reference
        stages scheduled before them.
        """
        seen: set[StageId] = set()
        for stage in stages:
            if stage.name in seen:
                raise PipelineConfigurationError.duplicate_stage_id(stage.name)
            for dependency in stage.depends_on:
                if dependency not in seen:
                    raise PipelineConfigurationError.dependency_not_scheduled(
                        stage.name, dependency
                    )
            seen.add(stage.name)
