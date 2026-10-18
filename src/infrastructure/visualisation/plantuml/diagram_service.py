"""Diagram generation service joining source building and image rendering."""

from typing import cast

from domain.models.topology import ArchitectureGraph
from infrastructure.visualisation.plantuml.c4_container_builder import (
    C4ContainerDiagramBuilder,
)
from infrastructure.visualisation.plantuml.models import (
    DiagramArtifacts,
    DiagramImageFormat,
)
from infrastructure.visualisation.plantuml.ports import DiagramSourceBuilder
from infrastructure.visualisation.plantuml.renderer import (
    AUTO_SERVER_SELECTION,
    PlantumlImageRenderer,
    resolve_image_renderer,
)


class DiagramService[SubjectT = ArchitectureGraph]:
    """Turns a typed diagram subject into source and rendered image bytes."""

    def __init__(
        self,
        source_builder: DiagramSourceBuilder[SubjectT] | None = None,
        image_renderer: PlantumlImageRenderer | None = None,
        image_format: DiagramImageFormat = DiagramImageFormat.SVG,
    ) -> None:
        if source_builder is None:
            self._source_builder: DiagramSourceBuilder[SubjectT] = cast(
                "DiagramSourceBuilder[SubjectT]", C4ContainerDiagramBuilder()
            )
        else:
            self._source_builder = source_builder
        self._image_renderer: PlantumlImageRenderer = (
            image_renderer
            if image_renderer is not None
            else resolve_image_renderer(AUTO_SERVER_SELECTION)
        )
        self._image_format: DiagramImageFormat = image_format

    def generate(self, subject: SubjectT, title: str | None = None) -> DiagramArtifacts:
        source: str = self._source_builder.build(subject, title)
        return DiagramArtifacts(
            source=source,
            image_url=self._image_renderer.build_image_url(source, self._image_format),
            image_format=self._image_format,
        )

    def render_image(self, artifacts: DiagramArtifacts) -> bytes:
        return self._image_renderer.render(artifacts.source, artifacts.image_format)
