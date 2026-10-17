"""PlantUML implementations of application.pipeline.ports.DiagramRenderer.

Contract: expected visualization errors (DiagramRenderingError,
DiagramSavingError) are converted to warnings. Any other exception is a
programming error and is propagated.

This module is diagram-type agnostic: the concrete ``DiagramSourceBuilder``
injected into ``PlantUmlDiagramRenderer`` decides what is rendered. Adding a
new diagram type means implementing a builder and wiring it once in the
composition root; this module does not change.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from application.pipeline.outcome import DiagramRenderResult
from infrastructure.visualisation.plantuml import (
    DiagramFileWriter,
    DiagramImageFormat,
    DiagramRenderingError,
    DiagramSavingError,
    DiagramService,
    DiagramSourceBuilder,
    resolve_image_renderer,
)

_logger = logging.getLogger("pipeline.diagram")


class PlantUmlDiagramRenderer[SubjectT]:
    """Generic PlantUML renderer driven by an injected source builder.

    The renderer is diagram-type agnostic: ``source_builder`` decides what
    is rendered. Adding a new diagram type only requires a new
    ``DiagramSourceBuilder`` implementation and one wiring line in
    ``infrastructure.composition``.
    """

    def __init__(
        self,
        *,
        source_builder: DiagramSourceBuilder,
        server: str,
        image_format: DiagramImageFormat,
    ) -> None:
        self._source_builder: DiagramSourceBuilder = source_builder
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
    service_factory: Callable[[], DiagramService],
    subject: SubjectT,
    title: str,
    base_name: str,
    out_dir: Path,
) -> DiagramRenderResult:
    """Builds the service, generates source, renders, writes.

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
