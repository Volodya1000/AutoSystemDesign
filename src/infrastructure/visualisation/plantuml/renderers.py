"""PlantUML implementations of application.pipeline.ports.DiagramRenderer.

Contract: expected visualization errors (DiagramRenderingError,
DiagramSavingError) are converted to warnings. Any other exception is a
programming error and is propagated.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from application.pipeline.outcome import DiagramRenderResult
from domain.models.sequence import InteractionScenario
from domain.models.topology import ArchitectureGraph
from infrastructure.visualisation.plantuml import (
    DiagramFileWriter,
    DiagramImageFormat,
    DiagramRenderingError,
    DiagramSavingError,
    DiagramService,
    resolve_image_renderer,
)
from infrastructure.visualisation.plantuml.sequence_builder import (
    SequenceDiagramBuilder,
)

_logger = logging.getLogger("pipeline.diagram")


class PlantUmlC4Renderer:
    def __init__(self, *, server: str, image_format: DiagramImageFormat) -> None:
        self._server: str = server
        self._image_format: DiagramImageFormat = image_format

    def render(
        self,
        subject: ArchitectureGraph,
        *,
        title: str,
        base_name: str,
        out_dir: Path,
    ) -> DiagramRenderResult:
        return _render_and_write(
            service_factory=lambda: DiagramService(
                image_renderer=resolve_image_renderer(self._server),
                image_format=self._image_format,
            ),
            subject=subject,
            title=title,
            base_name=base_name,
            out_dir=out_dir,
        )


class PlantUmlSequenceRenderer:
    def __init__(self, *, server: str, image_format: DiagramImageFormat) -> None:
        self._server: str = server
        self._image_format: DiagramImageFormat = image_format

    def render(
        self,
        subject: InteractionScenario,
        *,
        title: str,
        base_name: str,
        out_dir: Path,
    ) -> DiagramRenderResult:
        return _render_and_write(
            service_factory=lambda: DiagramService(
                source_builder=SequenceDiagramBuilder(),
                image_renderer=resolve_image_renderer(self._server),
                image_format=self._image_format,
            ),
            subject=subject,
            title=title,
            base_name=base_name,
            out_dir=out_dir,
        )


def _render_and_write(
    *,
    service_factory: Callable[[], DiagramService],
    subject: ArchitectureGraph | InteractionScenario,
    title: str,
    base_name: str,
    out_dir: Path,
) -> DiagramRenderResult:
    """Builds the service, generates source, renders, writes; never raises
    for expected visualization errors."""
    warnings: list[str] = []

    # Service construction + source generation: both are treated as
    # rendering-side operations and must not surface as exceptions for
    # expected failures.
    try:
        service = service_factory()
        artifacts = service.generate(subject, title=title)
    except (DiagramRenderingError, DiagramSavingError) as error:
        warning = f"Diagram source generation failed for {base_name}: {error}"
        _logger.warning(warning)
        return DiagramRenderResult(warnings=(warning,))

    image_rendered: bool = False
    try:
        image_bytes = service.render_image(artifacts)
    except DiagramRenderingError as error:
        warning = f"Rendering failed for {base_name}: {error}"
        _logger.warning(warning)
        warnings.append(warning)
    else:
        artifacts = artifacts.with_image(image_bytes)
        image_rendered = True

    try:
        written = DiagramFileWriter().write(artifacts, out_dir, base_name)
    except DiagramSavingError as error:
        warning = f"Saving diagram failed for {base_name}: {error}"
        _logger.warning(warning)
        warnings.append(warning)
        return DiagramRenderResult(
            artifacts=(),
            warnings=tuple(warnings),
            image_rendered=image_rendered,
        )

    for path in written:
        _logger.info("Diagram artifact written: %s", path)
    return DiagramRenderResult(
        artifacts=tuple(written),
        warnings=tuple(warnings),
        image_rendered=image_rendered,
    )
