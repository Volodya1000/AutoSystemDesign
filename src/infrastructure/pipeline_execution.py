"""Execute the configured design pipeline without CLI concerns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from infrastructure.composition import build_pipeline

if TYPE_CHECKING:
    from pathlib import Path

    from application.pipeline.protocols import PipelineReporterProtocol
    from config.root import AppSettings
    from domain.models import DesignScenario
    from infrastructure.visualisation.plantuml import DiagramImageFormat


@dataclass(frozen=True)
class PipelineExecutionOptions:
    """Resolved per-run overrides independent of the command-line parser."""

    out_dir: Path
    diagram_server: str
    diagram_format: DiagramImageFormat
    render_diagrams: bool = True


def execute_pipeline(
    scenario: DesignScenario,
    settings: AppSettings,
    options: PipelineExecutionOptions,
    *,
    reporter: PipelineReporterProtocol | None = None,
) -> int:
    """Build and run every stage against one typed scenario."""
    options.out_dir.mkdir(parents=True, exist_ok=True)
    wiring = build_pipeline(
        settings=settings,
        diagram_server=options.diagram_server,
        image_format=options.diagram_format,
        render_diagrams=options.render_diagrams,
        pipeline_reporter=reporter,
    )
    return wiring.runner.run(scenario, options.out_dir, wiring.writer)
