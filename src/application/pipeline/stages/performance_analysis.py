"""Stage that writes the performance report from the C4 graph and workload."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from application.performance_analysis.report_builder import (
    build_performance_analysis_report,
)
from application.pipeline.context import StageContext, require_payload
from application.pipeline.outcome import StageOutcome, StageStatus
from domain.models.topology import ArchitectureGraph

if TYPE_CHECKING:
    from domain.performance_analysis.report import PerformanceAnalysisReport


class PerformanceAnalysisStage:
    """Persist a report without changing pipeline orchestration or domain formulas.

    Report completeness is represented by PerformanceAnalysisStatus in the
    payload. StageStatus describes whether the required report artifact exists,
    so an unavailable analysis is still a successful stage result.
    """

    name: str = "performance_analysis"
    depends_on: tuple[str, ...] = ("c4",)

    def run(
        self, context: StageContext
    ) -> StageOutcome[PerformanceAnalysisReport]:
        stage_start: float = time.perf_counter()
        graph: ArchitectureGraph = require_payload(
            context, self.depends_on[0], ArchitectureGraph
        )
        report: PerformanceAnalysisReport = build_performance_analysis_report(
            graph, context.scenario
        )
        artifact_filename: str = (
            f"{context.scenario.identifier}_performance_analysis.json"
        )
        artifact_path = context.writer.write_text(
            context.out_dir / artifact_filename,
            report.model_dump_json(indent=2),
        )

        return StageOutcome(
            name=self.name,
            status=StageStatus.SUCCEEDED,
            duration_seconds=time.perf_counter() - stage_start,
            total_tokens=0,
            artifacts=(artifact_path,),
            payload=report,
        )
