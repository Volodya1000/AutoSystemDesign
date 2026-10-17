"""Stage 2: roles catalog + per-requirement sequence diagrams."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Protocol

from application.pipeline.context import StageContext, require_payload
from application.pipeline.outcome import StageOutcome, StageStatus
from application.pipeline.ports import DiagramRenderer, GenerationReporter
from application.pipeline.services import SequenceGenerator
from application.results import GenerationAttempt, SequenceGenerationResult
from domain.models import DesignScenario
from domain.models.sequence import InteractionScenario
from domain.models.topology import ArchitectureGraph

_logger = logging.getLogger("pipeline.sequence")

_SAFE_ID_PATTERN: re.Pattern[str] = re.compile(r"[^A-Za-z0-9_]")


class _InteractionResult(Protocol):
    @property
    def attempts(self) -> Sequence[GenerationAttempt]: ...

    @property
    def interaction_scenario(self) -> InteractionScenario | None: ...


def plan_base_names(
    scenario_id: str,
    requirement_ids: Iterable[str],
) -> Mapping[str, str]:
    """Precomputes unique base names; detects normalization collisions.

    "REQ-1" and "REQ_1" both normalize to "req_1" and would overwrite each
    other's artifacts. Refuse to silently lose data.
    """
    base_names: dict[str, str] = {}
    seen: dict[str, str] = {}
    for req_id in requirement_ids:
        safe_id: str = _SAFE_ID_PATTERN.sub("_", req_id).lower()
        previous: str | None = seen.get(safe_id)
        if previous is not None:
            raise ValueError(
                f"Requirement identifier collision: '{previous}' and "
                f"'{req_id}' both normalize to '{safe_id}'. Rename one of "
                f"them in the scenario so artifacts stay distinct."
            )
        seen[safe_id] = req_id
        base_names[req_id] = f"{scenario_id}_seq_{safe_id}"
    return base_names


def _functional_requirement_ids(scenario: DesignScenario) -> list[str]:
    """Best-effort extraction of functional-requirement identifiers.

    Supports both common layouts and returns [] when the model does not
    expose them; a fail-fast check is only possible when they are visible.
    """
    ids: list[str] = []

    functional = getattr(scenario, "functional_requirements", None)
    if functional:
        for req in functional:
            identifier = getattr(req, "identifier", None)
            if identifier:
                ids.append(str(identifier))
        return ids

    for req in getattr(scenario, "requirements", []) or []:
        if getattr(req, "type_identifier", None) == "functional":
            identifier = getattr(req, "identifier", None)
            if identifier:
                ids.append(str(identifier))
    return ids


class SequenceStage:
    name: str = "sequence"
    depends_on: tuple[str, ...] = ("c4",)

    def __init__(
        self,
        service: SequenceGenerator,
        renderer: DiagramRenderer[InteractionScenario] | None,
        reporter: GenerationReporter,
    ) -> None:
        self._service: SequenceGenerator = service
        self._renderer: DiagramRenderer[InteractionScenario] | None = renderer
        self._reporter: GenerationReporter = reporter

    def run(
        self, context: StageContext
    ) -> StageOutcome[dict[str, InteractionScenario]]:
        upstream_name: str = self.depends_on[0]
        graph: ArchitectureGraph = require_payload(
            context, upstream_name, ArchitectureGraph
        )
        scenario = context.scenario

        early_collision_error = self._check_early_collisions(scenario)
        if early_collision_error is not None:
            _logger.error("Identifier collision: %s", early_collision_error)
            return self._failed(0.0, 0, early_collision_error)

        stage_start: float = time.perf_counter()
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
            _logger.error("Identifier collision: %s", error)
            return self._failed(
                time.perf_counter() - stage_start,
                result.total_usage.total_tokens,
                str(error),
            )

        artifacts: list[Path] = self._write_roles_catalog(context, result)
        req_artifacts, warnings = self._process_all_requirements(
            context, base_names, result.scenarios_results
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
        early_ids = _functional_requirement_ids(scenario)
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

    def _write_roles_catalog(
        self,
        context: StageContext,
        result: SequenceGenerationResult,
    ) -> list[Path]:
        if result.roles_catalog is None:
            return []
        return [
            context.writer.write_text(
                context.out_dir / f"{context.scenario.identifier}_roles.json",
                result.roles_catalog.model_dump_json(indent=2),
            )
        ]

    def _process_all_requirements(
        self,
        context: StageContext,
        base_names: Mapping[str, str],
        scenarios_results: Mapping[str, _InteractionResult],
    ) -> tuple[list[Path], list[str]]:
        artifacts: list[Path] = []
        warnings: list[str] = []
        for req_id, req_result in scenarios_results.items():
            req_artifacts, req_warnings = self._process_requirement(
                context, base_names[req_id], req_id, req_result
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
    ) -> tuple[list[Path], list[str]]:
        self._reporter.attempts(
            req_result.attempts, f"Interaction attempts for {req_id}"
        )

        interaction: InteractionScenario | None = req_result.interaction_scenario
        if interaction is None:
            warning = f"Failed to generate sequence diagram for requirement: {req_id}"
            _logger.warning(warning)
            return [], [warning]

        artifacts: list[Path] = [
            context.writer.write_text(
                context.out_dir / f"{base_name}_ast.json",
                interaction.model_dump_json(indent=2),
            )
        ]
        warnings: list[str] = []
        if self._renderer is not None:
            render_result = self._renderer.render(
                interaction,
                title=interaction.description,
                base_name=base_name,
                out_dir=context.out_dir,
            )
            artifacts.extend(render_result.artifacts)
            warnings.extend(render_result.warnings)
        return artifacts, warnings

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
