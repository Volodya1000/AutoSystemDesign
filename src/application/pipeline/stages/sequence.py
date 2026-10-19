"""Stage 2: roles catalog + per-requirement sequence diagrams.

Pure naming and requirement-extraction helpers live in ``_naming.py``;
this module owns only stage orchestration, artifact persistence, and
per-requirement result handling.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Protocol

from application.pipeline.context import StageContext, require_payload
from application.pipeline.outcome import StageOutcome, StageStatus
from application.pipeline.sequence_artifacts import SequenceArtifactProcessor
from application.pipeline.stages._naming import (
    functional_requirement_ids,
    plan_base_names,
)
from domain.models.topology import ArchitectureGraph

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from application.pipeline.diagram_subjects import SequenceDiagramSubject
    from application.pipeline.ports import DiagramRenderer, GenerationReporter
    from application.pipeline.sequence_artifact_models import SequenceArtifactResult
    from application.pipeline.services import SequenceGenerator
    from application.results import GenerationAttempt, SequenceGenerationResult
    from domain.models import DesignScenario
    from domain.models.sequence import InteractionScenario

__all__ = ["SequenceStage", "plan_base_names"]

_logger = logging.getLogger("pipeline.sequence")


class _InteractionResult(Protocol):
    @property
    def attempts(self) -> Sequence[GenerationAttempt]: ...

    @property
    def interaction_scenario(self) -> InteractionScenario | None: ...


class SequenceStage:
    name: str = "sequence"
    depends_on: tuple[str, ...] = ("c4",)

    def __init__(
        self,
        service: SequenceGenerator,
        renderer: DiagramRenderer[SequenceDiagramSubject] | None,
        reporter: GenerationReporter,
    ) -> None:
        self._service: SequenceGenerator = service
        self._artifact_processor: SequenceArtifactProcessor = SequenceArtifactProcessor(
            renderer
        )
        self._reporter: GenerationReporter = reporter

    def run(
        self, context: StageContext
    ) -> StageOutcome[dict[str, InteractionScenario]]:
        stage_start: float = time.perf_counter()
        scenario: DesignScenario = context.scenario

        if not scenario.functional_requirements:
            _logger.info(
                "No functional requirements provided; skipping sequence generation."
            )
            return StageOutcome(
                name=self.name,
                status=StageStatus.SUCCEEDED,
                duration_seconds=time.perf_counter() - stage_start,
                total_tokens=0,
                payload={},
                message=(
                    "No functional requirements provided; "
                    "skipping sequence generation."
                ),
            )

        upstream_name: str = self.depends_on[0]
        graph: ArchitectureGraph = require_payload(
            context, upstream_name, ArchitectureGraph
        )
        early_collision_error: str | None = self._check_early_collisions(scenario)
        if early_collision_error is not None:
            _logger.error("Identifier collision: %s", early_collision_error)
            return self._failed(0.0, 0, early_collision_error)

        generation_start: float = time.perf_counter()
        result: SequenceGenerationResult = self._service.generate(scenario, graph)
        generation_seconds: float = time.perf_counter() - generation_start

        _logger.info(
            "Sequence generation finished in %.1f s (generation)",
            generation_seconds,
        )
        self._reporter.attempts(result.roles_attempts, "Roles catalog attempts")
        self._reporter.tokens(result.total_usage, generation_seconds)

        try:
            base_names: Mapping[str, str] = plan_base_names(
                scenario.identifier, list(result.scenarios_results)
            )
        except ValueError as error:
            _logger.exception("Identifier collision")
            return self._failed(
                time.perf_counter() - stage_start,
                result.total_usage.total_tokens,
                str(error),
            )

        artifacts: list[Path] = list(
            self._artifact_processor.persist_roles_catalog(
                context, result.roles_catalog
            )
        )
        # ``graph`` is forwarded so ``_process_requirement`` can build a
        # ``SequenceDiagramSubject`` that carries both the scenario and the
        # C4 topology to the renderer (see ``_process_requirement``).
        req_artifacts: list[Path]
        warnings: list[str]
        req_artifacts, warnings = self._process_all_requirements(
            context, base_names, result.scenarios_results, graph
        )
        artifacts.extend(req_artifacts)

        return StageOutcome(
            name=self.name,
            status=self._compute_status(result, warnings),
            duration_seconds=time.perf_counter() - stage_start,
            total_tokens=result.total_usage.total_tokens,
            artifacts=tuple(artifacts),
            payload=self._extract_successful_scenarios(result),
            warnings=tuple(warnings),
        )

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _check_early_collisions(scenario: DesignScenario) -> str | None:
        early_ids: Sequence[str] = functional_requirement_ids(scenario)
        if early_ids:
            try:
                plan_base_names(scenario.identifier, early_ids)
            except ValueError as error:
                return str(error)
        return None

    @staticmethod
    def _extract_successful_scenarios(
        result: SequenceGenerationResult,
    ) -> dict[str, InteractionScenario]:
        return {
            req_id: req_res.interaction_scenario
            for req_id, req_res in result.scenarios_results.items()
            if req_res.interaction_scenario is not None
        }

    def _failed(
        self,
        duration_seconds: float,
        total_tokens: int,
        message: str,
    ) -> StageOutcome[dict[str, InteractionScenario]]:
        return StageOutcome(
            name=self.name,
            status=StageStatus.FAILED,
            duration_seconds=duration_seconds,
            total_tokens=total_tokens,
            payload=None,
            message=message,
        )

    def _process_all_requirements(
        self,
        context: StageContext,
        base_names: Mapping[str, str],
        scenarios_results: Mapping[str, _InteractionResult],
        graph: ArchitectureGraph,
    ) -> tuple[list[Path], list[str]]:
        artifacts: list[Path] = []
        warnings: list[str] = []
        for req_id, req_result in scenarios_results.items():
            req_artifacts: list[Path]
            req_warnings: list[str]
            req_artifacts, req_warnings = self._process_requirement(
                context, base_names[req_id], req_id, req_result, graph
            )
            artifacts.extend(req_artifacts)
            warnings.extend(req_warnings)
        return artifacts, warnings

    def _process_requirement(
        self,
        context: StageContext,
        base_name: str,
        req_id: str,
        req_result: _InteractionResult,
        graph: ArchitectureGraph,
    ) -> tuple[list[Path], list[str]]:
        self._reporter.attempts(
            req_result.attempts, f"Interaction attempts for {req_id}"
        )

        interaction: InteractionScenario | None = req_result.interaction_scenario
        if interaction is None:
            warning: str = (
                f"Failed to generate sequence diagram for requirement: {req_id}"
            )
            _logger.warning(warning)
            return [], [warning]

        artifact_result: SequenceArtifactResult = (
            self._artifact_processor.persist_interaction(
                context,
                base_name=base_name,
                interaction=interaction,
                graph=graph,
            )
        )
        return list(artifact_result.artifacts), list(artifact_result.warnings)

    @staticmethod
    def _compute_status(
        result: SequenceGenerationResult,
        warnings: Sequence[str],
    ) -> StageStatus:
        if not result.is_successful:
            return StageStatus.FAILED
        if warnings:
            return StageStatus.PARTIAL
        return StageStatus.SUCCEEDED
