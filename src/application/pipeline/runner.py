"""Ordered execution of stages. Contains no domain logic.

Exit-code contract:
    0 - every stage produced its required artifacts (SUCCEEDED or PARTIAL)
    1 - at least one stage FAILED (required artifacts missing)
    2 - configuration, scenario, or LLM endpoint failure (handled by CLI)
"""

from __future__ import annotations

import logging
from types import MappingProxyType
from typing import TYPE_CHECKING

from application.pipeline.context import StageContext
from application.pipeline.outcome import StageOutcome, StageStatus

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from application.pipeline.ports import ArtifactWriter, PipelineReporter
    from application.pipeline.stage import PipelineStage
    from domain.models import DesignScenario

_logger = logging.getLogger("pipeline.runner")


class PipelineConfigurationError(ValueError):
    """Invalid stage configuration for the pipeline runner."""

    @classmethod
    def no_stages(cls) -> PipelineConfigurationError:
        return cls("PipelineRunner requires at least one stage")

    @classmethod
    def duplicate_stage_name(cls, stage_name: str) -> PipelineConfigurationError:
        return cls(
            f"Duplicate stage name '{stage_name}'; stage names must "
            "be unique because outcomes are keyed by name"
        )

    @classmethod
    def dependency_not_scheduled(
        cls, stage_name: str, dependency: str
    ) -> PipelineConfigurationError:
        return cls(
            f"Stage '{stage_name}' depends on '{dependency}', "
            "which is not scheduled before it"
        )


class PipelineRunner:
    def __init__(
        self,
        stages: Sequence[PipelineStage],
        reporter: PipelineReporter,
    ) -> None:
        stages_tuple: tuple[PipelineStage, ...] = tuple(stages)
        if not stages_tuple:
            raise PipelineConfigurationError.no_stages()
        self._validate_stages(stages_tuple)
        self._stages: tuple[PipelineStage, ...] = stages_tuple
        self._reporter: PipelineReporter = reporter

    def run(
        self,
        scenario: DesignScenario,
        out_dir: Path,
        writer: ArtifactWriter,
    ) -> int:
        upstream: dict[str, StageOutcome[object]] = {}
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
                self._reporter.report(outcomes)
                return 1

        self._reporter.report(outcomes)
        # PARTIAL is not a failure: diagram rendering is best-effort by
        # design. Required artifacts (JSON graph, roles catalog, ASTs) are
        # produced whenever the stage is not FAILED. Callers that want to
        # gate on diagrams should inspect the summary line instead of the
        # exit code.
        return 0

    @staticmethod
    def _validate_stages(stages: tuple[PipelineStage, ...]) -> None:
        """Validates stage-name uniqueness and dependency ordering.

        Results are keyed by stage name in ``upstream``, so duplicate names
        would silently overwrite each other; dependencies must reference
        stages scheduled before them.
        """
        seen: set[str] = set()
        for stage in stages:
            if stage.name in seen:
                raise PipelineConfigurationError.duplicate_stage_name(stage.name)
            for dependency in stage.depends_on:
                if dependency not in seen:
                    raise PipelineConfigurationError.dependency_not_scheduled(
                        stage.name, dependency
                    )
            seen.add(stage.name)
