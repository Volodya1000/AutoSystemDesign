"""Stage 1: C4 architecture generation."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from application.pipeline.outcome import DiagramRenderResult, StageOutcome, StageStatus
from application.pipeline.stage import StageId
from application.requirement_coverage import build_requirement_coverage_report
from application.results import DesignGenerationResult, GenerationStatus
from domain.models.requirement_coverage import (
    RequirementCheckStatus,
    RequirementCoverageReport,
)
from domain.specifications.metrics import (
    ProjectMetrics,
    compute_project_metrics,
    format_metrics_title,
)

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
        result: DesignGenerationResult = self._service.generate(scenario)
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

        # Persist even an invalid graph: it is the primary diagnostic artifact.
        if graph is not None:
            artifacts.append(
                context.writer.write_text(
                    context.out_dir / f"{scenario.identifier}_c4.json",
                    graph.model_dump_json(indent=2),
                )
            )

        if scenario.requirements:
            coverage: RequirementCoverageReport = build_requirement_coverage_report(
                scenario,
                graph_accepted=result.status is GenerationStatus.SUCCEEDED,
                validation=result.attempts[-1].validation,
            )
            artifacts.append(
                context.writer.write_text(
                    context.out_dir / f"{scenario.identifier}_nfr_coverage.json",
                    coverage.model_dump_json(indent=2),
                )
            )
            unchecked: int = sum(
                item.status is RequirementCheckStatus.NOT_EVALUATED
                for item in coverage.requirements
            )
            if unchecked:
                warnings.append(
                    f"{unchecked} NFR requirement(s) not evaluated; "
                    "see the NFR coverage JSON artifact"
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

        render_result: DiagramRenderResult = self._render(
            graph, scenario, context.out_dir
        )
        artifacts.extend(render_result.artifacts)
        warnings.extend(render_result.warnings)

        # Unverified NFRs warn; only optional rendering errors make C4 partial.
        status: StageStatus = StageStatus.SUCCEEDED
        if render_result.warnings:
            status = StageStatus.PARTIAL
        return StageOutcome(
            name=self.name,
            status=status,
            duration_seconds=time.perf_counter() - stage_start,
            total_tokens=result.total_usage.total_tokens,
            artifacts=tuple(artifacts),
            payload=graph,
            warnings=tuple(warnings),
        )

    def _render(
        self,
        graph: ArchitectureGraph,
        scenario: DesignScenario,
        out_dir: Path,
    ) -> DiagramRenderResult:
        """Render an optional diagram independently of NFR coverage warnings."""
        if self._renderer is None:
            return DiagramRenderResult()
        title: str = f"C4 Container: {scenario.identifier}"
        metrics: ProjectMetrics = compute_project_metrics(graph, scenario)
        summary: str = format_metrics_title(metrics)
        if summary:
            title = f"{title}\n{summary}"
        return self._renderer.render(
            graph,
            title=title,
            base_name=f"{scenario.identifier}_c4",
            out_dir=out_dir,
        )
