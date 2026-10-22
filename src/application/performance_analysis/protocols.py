"""Application protocols for alternative performance-report renderers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.performance_analysis.report import PerformanceAnalysisReport


class PdfRenderingUnavailableError(RuntimeError):
    """Optional PDF output cannot be rendered in this environment."""


class PerformanceReportPdfRendererProtocol(Protocol):
    """Render an already calculated report into PDF bytes, without I/O."""

    def render(self, report: PerformanceAnalysisReport) -> bytes: ...
