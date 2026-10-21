"""Diagram generation service joining source building and image rendering."""

from __future__ import annotations

from typing import TYPE_CHECKING, overload

from domain.models.topology import ArchitectureGraph
from infrastructure.visualisation.plantuml.c4_container_builder import (
    C4ContainerDiagramBuilder,
)
from infrastructure.visualisation.plantuml.models import (
    DiagramArtifacts,
    DiagramImageFormat,
)
from infrastructure.visualisation.plantuml.renderer import (
    AUTO_SERVER_SELECTION,
    PlantumlImageRendererProtocol,
    resolve_image_renderer,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from infrastructure.visualisation.plantuml.protocols import (
        DiagramSourceBuilderProtocol,
    )


class UnsupportedDiagramSubjectError(TypeError):
    """The default C4 builder received a subject of another domain type."""

    def __init__(self) -> None:
        super().__init__(
            "The default DiagramService builder accepts ArchitectureGraph; "
            "inject a matching source_builder for other subject types."
        )


class DiagramService[SubjectT = ArchitectureGraph]:
    """Turns a typed diagram subject into source and rendered image bytes.

    Omitting source_builder selects the legacy C4 path and is only valid for
    ArchitectureGraph. Other diagram types must inject a matching builder.
    """

    @overload
    def __init__(
        self: DiagramService[ArchitectureGraph],
        source_builder: None = None,
        image_renderer: PlantumlImageRendererProtocol | None = None,
        image_format: DiagramImageFormat = DiagramImageFormat.SVG,
    ) -> None: ...

    @overload
    def __init__(
        self,
        source_builder: DiagramSourceBuilderProtocol[SubjectT],
        image_renderer: PlantumlImageRendererProtocol | None = None,
        image_format: DiagramImageFormat = DiagramImageFormat.SVG,
    ) -> None: ...

    def __init__(
        self,
        source_builder: DiagramSourceBuilderProtocol[SubjectT] | None = None,
        image_renderer: PlantumlImageRendererProtocol | None = None,
        image_format: DiagramImageFormat = DiagramImageFormat.SVG,
    ) -> None:
        self._build_source: Callable[[SubjectT, str | None], str]
        if source_builder is None:

            def build_default_source(subject: SubjectT, title: str | None) -> str:
                # Keep runtime safety even if callers bypass static type checking.
                if not isinstance(subject, ArchitectureGraph):
                    raise UnsupportedDiagramSubjectError
                return C4ContainerDiagramBuilder().build(subject, title)

            self._build_source = build_default_source
        else:
            self._build_source = source_builder.build

        self._image_renderer: PlantumlImageRendererProtocol = (
            image_renderer
            if image_renderer is not None
            else resolve_image_renderer(AUTO_SERVER_SELECTION)
        )
        self._image_format: DiagramImageFormat = image_format

    def generate(self, subject: SubjectT, title: str | None = None) -> DiagramArtifacts:
        """Build source for the typed subject and prepare its rendering URL."""
        source: str = self._build_source(subject, title)
        return DiagramArtifacts(
            source=source,
            image_url=self._image_renderer.build_image_url(source, self._image_format),
            image_format=self._image_format,
        )

    def render_image(self, artifacts: DiagramArtifacts) -> bytes:
        """Render the previously prepared source into image bytes."""
        return self._image_renderer.render(artifacts.source, artifacts.image_format)
