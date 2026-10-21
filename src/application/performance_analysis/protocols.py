"""Application protocols for alternative performance-report renderers."""

from __future__ import annotations

from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from domain.performance_analysis.report import PerformanceAnalysisReport


class PerformanceReportPdfRendererProtocol(Protocol):
    """Render an already calculated report into PDF bytes, without I/O."""

    def render(self, report: PerformanceAnalysisReport) -> bytes: ...
