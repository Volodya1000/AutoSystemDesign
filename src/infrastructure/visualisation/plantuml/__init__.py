"""PlantUML diagram generation from an ArchitectureGraph."""

from infrastructure.visualisation.plantuml.c4_container_builder import (
    C4_STDLIB_BUNDLED_INCLUDE,
    C4_STDLIB_REMOTE_INCLUDE_URL,
    C4ContainerDiagramBuilder,
)
from infrastructure.visualisation.plantuml.diagram_service import DiagramService
from infrastructure.visualisation.plantuml.diagram_writer import (
    DiagramFileWriter,
    DiagramSavingError,
)
from infrastructure.visualisation.plantuml.element_specs import (
    DEFAULT_ELEMENT_SPECS,
    C4ElementSpec,
)
from infrastructure.visualisation.plantuml.encoding import (
    build_kroki_url,
    build_plantuml_url,
    encode_kroki_text,
    encode_plantuml_text,
)
from infrastructure.visualisation.plantuml.models import (
    DiagramArtifacts,
    DiagramImageFormat,
)
from infrastructure.visualisation.plantuml.ports import DiagramSourceBuilder
from infrastructure.visualisation.plantuml.renderer import (
    AUTO_SERVER_SELECTION,
    KROKI_PUBLIC_SERVER_URL,
    PLANTUML_PUBLIC_SERVER_URL,
    DiagramRenderingError,
    FallbackImageRenderer,
    KrokiImageRenderer,
    PlantumlImageRenderer,
    PlantumlServerImageRenderer,
    resolve_image_renderer,
)
from infrastructure.visualisation.plantuml.sequence_builder import (
    SequenceDiagramBuilder,
)

__all__ = [
    "AUTO_SERVER_SELECTION",
    "C4_STDLIB_BUNDLED_INCLUDE",
    "C4_STDLIB_REMOTE_INCLUDE_URL",
    "DEFAULT_ELEMENT_SPECS",
    "KROKI_PUBLIC_SERVER_URL",
    "PLANTUML_PUBLIC_SERVER_URL",
    "C4ContainerDiagramBuilder",
    "C4ElementSpec",
    "DiagramArtifacts",
    "DiagramFileWriter",
    "DiagramImageFormat",
    "DiagramRenderingError",
    "DiagramSavingError",
    "DiagramService",
    "DiagramSourceBuilder",
    "FallbackImageRenderer",
    "KrokiImageRenderer",
    "PlantumlImageRenderer",
    "PlantumlServerImageRenderer",
    "SequenceDiagramBuilder",
    "build_kroki_url",
    "build_plantuml_url",
    "encode_kroki_text",
    "encode_plantuml_text",
    "resolve_image_renderer",
]
