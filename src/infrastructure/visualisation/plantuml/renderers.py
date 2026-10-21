# Copyright (c) 2026 Volodya1000
"""PlantUML implementation of the DiagramRenderer port.

Contract: expected visualization errors (DiagramRenderingError,
DiagramSavingError) are converted to warnings. Any other exception is a
programming error and is propagated.

The renderer is diagram-type agnostic: ``source_builder`` decides what is
rendered. Adding a new diagram type only requires a new
``DiagramSourceBuilder`` implementation and one wiring line in
``infrastructure.composition``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from application.pipeline.outcome import DiagramRenderResult
from infrastructure.visualisation.plantuml import (
    DiagramFileWriter,
    DiagramImageFormat,
    DiagramRenderingError,
    DiagramSavingError,
    resolve_image_renderer,
)
from infrastructure.visualisation.plantuml.diagram_service import DiagramService

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from infrastructure.visualisation.plantuml.ports import DiagramSourceBuilder

_logger = logging.getLogger("pipeline.diagram")


class PlantUmlDiagramRenderer[SubjectT]:
    """Generic PlantUML renderer driven by an injected source builder."""

    def __init__(
        self,
        *,
        source_builder: DiagramSourceBuilder[SubjectT],
        server: str,
        image_format: DiagramImageFormat,
    ) -> None:
        self._source_builder: DiagramSourceBuilder[SubjectT] = source_builder
        self._server: str = server
        self._image_format: DiagramImageFormat = image_format

    def render(
        self,
        subject: SubjectT,
        *,
        title: str,
        base_name: str,
        out_dir: Path,
    ) -> DiagramRenderResult:
        return render_and_write(
            service_factory=lambda: DiagramService(
                source_builder=self._source_builder,
                image_renderer=resolve_image_renderer(self._server),
                image_format=self._image_format,
            ),
            subject=subject,
            title=title,
            base_name=base_name,
            out_dir=out_dir,
        )


def render_and_write[SubjectT](
    *,
    service_factory: Callable[[], DiagramService[SubjectT]],
    subject: SubjectT,
    title: str,
    base_name: str,
    out_dir: Path,
) -> DiagramRenderResult:
    """Build the service, generates source, renders, writes.

    Never raises for expected visualization errors: they become warnings.
    Unexpected exceptions (programming errors) propagate untouched.
    """
    warnings: list[str] = []

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
