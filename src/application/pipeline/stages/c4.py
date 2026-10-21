"""Stage 1: C4 architecture generation."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from application.pipeline.outcome import StageOutcome, StageStatus
from application.requirement_coverage import build_requirement_coverage_report
from application.pipeline.stage import StageId
from application.results import GenerationStatus
from domain.specifications.metrics import compute_project_metrics, format_metrics_title
from domain.models.requirement_coverage import RequirementCheckStatus

if TYPE_CHECKING:
    from pathlib import Path

    from application.pipeline.context import StageContext
    from application.pipeline.ports import DiagramRenderer, GenerationReporter
    from application.pipeline.services import DesignGenerator
    from domain.models.scenarios import DesignScenario
    from domain.models.topology import ArchitectureGraph

_logger = logging.getLogger("pipeline.c4")


class C4Stage:
    name: StageId = StageId.C4
    depends_on: tuple[StageId, ...] = ()

    def __init__(
        self,
        service: DesignGenerator,
        renderer: DiagramRenderer[ArchitectureGraph] | None,
        reporter: GenerationReporter,
    ) -> None:
        self._service: DesignGenerator = service
        self._renderer: DiagramRenderer[ArchitectureGraph] | None = renderer
        self._reporter: GenerationReporter = reporter

    def run(self, context: StageContext) -> StageOutcome[ArchitectureGraph]:
        stage_start: float = time.perf_counter()
        scenario: DesignScenario = context.scenario

        generation_start: float = time.perf_counter()
        result = self._service.generate(scenario)
        generation_seconds: float = time.perf_counter() - generation_start

        self._reporter.attempts(result.attempts, "C4 generation attempts")
        self._reporter.tokens(result.total_usage, generation_seconds)
        _logger.info(
            "C4 result: %s in %.1f s (generation)",
            result.status.value,
            generation_seconds,
        )

        artifacts: list[Path] = []
        warnings: list[str] = []
        graph: ArchitectureGraph | None = result.graph

        if scenario.requirements:
            coverage = build_requirement_coverage_report(scenario, result)
            artifacts.append(
                context.writer.write_text(
                    context.out_dir / f"{scenario.identifier}_nfr_coverage.json",
                    coverage.model_dump_json(indent=2),
                )
            )
            unchecked = sum(
                item.status is RequirementCheckStatus.NOT_EVALUATED
                for item in coverage.requirements
            )
            if unchecked:
                warnings.append(
                    f"{unchecked} NFR requirement(s) not evaluated; "
                    "see the NFR coverage JSON artifact"
                )

        # Persist even an invalid graph: it is the primary diagnostic artifact.
        if graph is not None:
            artifacts.append(
                context.writer.write_text(
                    context.out_dir / f"{scenario.identifier}_c4.json",
                    graph.model_dump_json(indent=2),
                )
            )

        if result.status is not GenerationStatus.SUCCEEDED or graph is None:
            return StageOutcome(
                name=self.name,
                status=StageStatus.FAILED,
                duration_seconds=time.perf_counter() - stage_start,
                total_tokens=result.total_usage.total_tokens,
                artifacts=tuple(artifacts),
                payload=None,
                message="C4 architecture generation failed",
                warnings=tuple(warnings),
            )

        if self._renderer is not None:
            title = f"C4 Container: {scenario.identifier}"
            metrics = compute_project_metrics(graph, scenario)
            summary = format_metrics_title(metrics)
            if summary:
                title = f"{title}\n{summary}"

            render_result = self._renderer.render(
                graph,
                title=title,
                base_name=f"{scenario.identifier}_c4",
                out_dir=context.out_dir,
            )
            artifacts.extend(render_result.artifacts)
            warnings.extend(render_result.warnings)

        status = StageStatus.PARTIAL if warnings else StageStatus.SUCCEEDED
        return StageOutcome(
            name=self.name,
            status=status,
            duration_seconds=time.perf_counter() - stage_start,
            total_tokens=result.total_usage.total_tokens,
            artifacts=tuple(artifacts),
            payload=graph,
            warnings=tuple(warnings),
        )
