"""Stage that writes the performance report from the C4 graph and workload."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from application.performance_analysis.protocols import (
    PdfRenderingUnavailableError,
    PerformanceReportPdfRendererProtocol,
)
from application.performance_analysis.report_builder import (
    build_performance_analysis_report,
)
from application.pipeline.context import StageContext, require_payload
from application.pipeline.outcome import StageOutcome, StageStatus
from application.pipeline.stage import StageId
from domain.models.topology import ArchitectureGraph
from domain.performance_analysis.report import PerformanceAnalysisReport

if TYPE_CHECKING:
    from pathlib import Path

    from domain.models.scenarios import DesignScenario


class PerformanceAnalysisStage:
    """Persist a report without changing pipeline orchestration or domain formulas.

    Report completeness is represented by PerformanceAnalysisStatus in the
    payload. StageStatus describes whether the required report artifact exists,
    so an unavailable analysis is still a successful stage result.
    """

    name: StageId = StageId.PERFORMANCE_ANALYSIS
    depends_on: tuple[StageId, ...] = (StageId.C4,)

    def __init__(
        self, pdf_renderer: PerformanceReportPdfRendererProtocol | None = None
    ) -> None:
        self._pdf_renderer = pdf_renderer

    def run(self, context: StageContext) -> StageOutcome[PerformanceAnalysisReport]:
        stage_start: float = time.perf_counter()
        scenario: DesignScenario = context.scenario
        graph: ArchitectureGraph = require_payload(
            context, self.depends_on[0], ArchitectureGraph
        )
        report: PerformanceAnalysisReport = build_performance_analysis_report(
            graph, scenario
        )
        artifact_filename: str = f"{scenario.identifier}_performance_analysis.json"
        artifact_path: Path = context.writer.write_text(
            context.out_dir / artifact_filename,
            report.model_dump_json(indent=2),
        )

        artifacts: tuple[Path, ...] = (artifact_path,)
        warnings: tuple[str, ...] = ()
        status = StageStatus.SUCCEEDED

        if self._pdf_renderer is not None:
            try:
                pdf_content = self._pdf_renderer.render(report)
                pdf_path = context.writer.write_bytes(
                    context.out_dir / f"{scenario.identifier}_performance_analysis.pdf",
                    pdf_content,
                )
                artifacts = (*artifacts, pdf_path)
            except (OSError, PdfRenderingUnavailableError) as exc:
                # JSON is mandatory and has already been persisted successfully.
                status = StageStatus.PARTIAL
                warnings = (f"Optional performance PDF unavailable: {exc}",)

        duration_seconds: float = time.perf_counter() - stage_start
        return StageOutcome[PerformanceAnalysisReport](
            name=self.name,
            status=status,
            duration_seconds=duration_seconds,
            total_tokens=0,
            artifacts=artifacts,
            payload=report,
            warnings=warnings,
        )
