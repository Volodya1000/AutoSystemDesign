from typing import Any, Protocol

from infrastructure.visualisation.plantuml.c4_container_builder import (
    C4ContainerDiagramBuilder,
)
from infrastructure.visualisation.plantuml.models import (
    DiagramArtifacts,
    DiagramImageFormat,
)
from infrastructure.visualisation.plantuml.renderer import (
    AUTO_SERVER_SELECTION,
    PlantumlImageRenderer,
    resolve_image_renderer,
)


class DiagramSourceBuilder(Protocol):
    def build(self, graph: Any, title: str | None = None) -> str: ...


class DiagramService:
    def __init__(
        self,
        source_builder: DiagramSourceBuilder | None = None,
        image_renderer: PlantumlImageRenderer | None = None,
        image_format: DiagramImageFormat = DiagramImageFormat.SVG,
    ) -> None:
        self._source_builder: DiagramSourceBuilder = (
            source_builder
            if source_builder is not None
            else C4ContainerDiagramBuilder()
        )
        self._image_renderer: PlantumlImageRenderer = (
            image_renderer
            if image_renderer is not None
            else resolve_image_renderer(AUTO_SERVER_SELECTION)
        )
        self._image_format: DiagramImageFormat = image_format

    def generate(self, graph: Any, title: str | None = None) -> DiagramArtifacts:
        source: str = self._source_builder.build(graph, title)
        return DiagramArtifacts(
            source=source,
            image_url=self._image_renderer.build_image_url(source, self._image_format),
            image_format=self._image_format,
        )

    def render_image(self, artifacts: DiagramArtifacts) -> bytes:
        return self._image_renderer.render(artifacts.source, artifacts.image_format)
