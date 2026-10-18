"""Stage 3: REST API Design generation and OpenAPI/Swagger artifacts persistence."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from pathlib import Path

from application.pipeline.context import StageContext, require_payload
from application.pipeline.outcome import DiagramRenderResult, StageOutcome, StageStatus
from application.pipeline.ports import ApiArtifactRenderer, GenerationReporter
from application.pipeline.services import ApiGenerator
from application.results import ApiGenerationResult, GenerationStatus
from domain.models.api import ApiDesign
from domain.models.sequence import InteractionScenario
from domain.models.topology import ArchitectureGraph

_logger: logging.Logger = logging.getLogger("pipeline.api")


class ApiStage:
    name: str = "api"
    depends_on: tuple[str, ...] = ("c4", "sequence")

    def __init__(
        self,
        service: ApiGenerator,
        renderer: ApiArtifactRenderer | None,
        reporter: GenerationReporter,
    ) -> None:
        self._service: ApiGenerator = service
        self._renderer: ApiArtifactRenderer | None = renderer
        self._reporter: GenerationReporter = reporter

    def run(self, context: StageContext) -> StageOutcome[ApiDesign]:
        stage_start: float = time.perf_counter()
        scenario = context.scenario

        if not scenario.functional_requirements:
            message = "No functional requirements provided; skipping API generation."
            _logger.info(message)
            return StageOutcome(
                name=self.name,
                status=StageStatus.SUCCEEDED,
                duration_seconds=time.perf_counter() - stage_start,
                total_tokens=0,
                payload=None,
                message=message,
            )

        graph: ArchitectureGraph = require_payload(context, "c4", ArchitectureGraph)
        sequences: Mapping[str, InteractionScenario] = require_payload(
            context, "sequence", dict
        )

        generation_start: float = time.perf_counter()
        result: ApiGenerationResult = self._service.generate(scenario, graph, sequences)
        generation_seconds: float = time.perf_counter() - generation_start

        self._reporter.attempts(result.attempts, "API generation attempts")
        self._reporter.tokens(result.total_usage, generation_seconds)
        _logger.info(
            "API design result: %s in %.1f s (generation)",
            result.status.value,
            generation_seconds,
        )

        artifacts: list[Path] = []
        warnings: list[str] = []
        api_design: ApiDesign | None = result.api_design

        if api_design is not None:
            artifacts.append(
                context.writer.write_text(
                    context.out_dir / f"{scenario.identifier}_api_design.json",
                    api_design.model_dump_json(indent=2),
                )
            )

        if result.status is not GenerationStatus.SUCCEEDED or api_design is None:
            return StageOutcome(
                name=self.name,
                status=StageStatus.FAILED,
                duration_seconds=time.perf_counter() - stage_start,
                total_tokens=result.total_usage.total_tokens,
                artifacts=tuple(artifacts),
                payload=None,
                message="REST API design generation failed",
            )

        if self._renderer is not None:
            render_result: DiagramRenderResult = self._renderer.render(
                api_design,
                title=f"{scenario.identifier} API",
                base_name=f"{scenario.identifier}_api",
                out_dir=context.out_dir,
            )
            artifacts.extend(render_result.artifacts)
            warnings.extend(render_result.warnings)

        status: StageStatus = StageStatus.PARTIAL if warnings else StageStatus.SUCCEEDED
        return StageOutcome(
            name=self.name,
            status=status,
            duration_seconds=time.perf_counter() - stage_start,
            total_tokens=result.total_usage.total_tokens,
            artifacts=tuple(artifacts),
            payload=api_design,
            warnings=tuple(warnings),
        )
