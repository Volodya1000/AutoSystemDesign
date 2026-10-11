"""Facade of the PlantUML diagram pipeline: graph in, artifacts out.

The service depends on two ports: a DiagramSourceBuilder (pure text
rendering of a graph; C4 Container is the current implementation, other
diagram kinds can be added without touching this class) and a
PlantumlImageRenderer (image transport). `generate` is offline and
cannot fail for a valid graph; `render_image` performs network I/O and
raises DiagramRenderingError, so the failure policy stays with callers.
"""

from typing import Protocol

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
    PlantumlImageRenderer,
    resolve_image_renderer,
)


class DiagramSourceBuilder(Protocol):
    """Port: renders an ArchitectureGraph as PlantUML diagram source."""

    def build(self, graph: ArchitectureGraph, title: str | None = None) -> str: ...


class DiagramService:
    """High-level entry point: ArchitectureGraph in, diagram artifacts out."""

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

    def generate(
        self, graph: ArchitectureGraph, title: str | None = None
    ) -> DiagramArtifacts:
        """Builds diagram artifacts from the graph; performs no network I/O."""
        source: str = self._source_builder.build(graph, title)
        return DiagramArtifacts(
            source=source,
            image_url=self._image_renderer.build_image_url(source, self._image_format),
            image_format=self._image_format,
        )

    def render_image(self, artifacts: DiagramArtifacts) -> bytes:
        """Renders the diagram image through the configured renderer.

        Raises DiagramRenderingError when every configured server fails.
        """
        return self._image_renderer.render(artifacts.source, artifacts.image_format)
