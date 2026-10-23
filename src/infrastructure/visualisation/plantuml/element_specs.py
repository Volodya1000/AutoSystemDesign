"""Mapping of domain node types onto C4-PlantUML element calls.

Kept apart from the builder so the presentation table can evolve (new
node types, other element choices) independently of the document
assembly logic.
"""

from dataclasses import dataclass
from typing import Final

from domain.models.enums import NodeType
from shared.artifact_language import ArtifactLanguage


@dataclass(frozen=True)
class C4ElementSpec:
    """C4-PlantUML element call used for one domain node type.

    An empty `technology` omits the technology argument: Person calls
    have no technology parameter, Container-family calls do.
    """

    function: str
    technology: str = ""


DEFAULT_ELEMENT_SPECS: Final[dict[NodeType, C4ElementSpec]] = {
    NodeType.CLIENT: C4ElementSpec(function="Person_Ext"),
    NodeType.LOAD_BALANCER: C4ElementSpec(
        function="Container", technology="Load Balancer"
    ),
    NodeType.COMPUTE: C4ElementSpec(function="Container", technology="Service"),
    NodeType.DATABASE: C4ElementSpec(function="ContainerDb", technology="Database"),
    NodeType.CACHE: C4ElementSpec(function="Container", technology="Cache"),
    NodeType.MESSAGE_BROKER: C4ElementSpec(
        function="ContainerQueue", technology="Message Broker"
    ),
}


def localized_element_specs(
    language: ArtifactLanguage,
) -> dict[NodeType, C4ElementSpec]:
    """Localize descriptive component types while preserving C4 functions."""
    if language is ArtifactLanguage.ENGLISH:
        return dict(DEFAULT_ELEMENT_SPECS)
    labels: dict[NodeType, str] = {
        NodeType.CLIENT: "",
        NodeType.LOAD_BALANCER: "Балансировщик",
        NodeType.COMPUTE: "Сервис",
        NodeType.DATABASE: "База данных",
        NodeType.CACHE: "Кэш",
        NodeType.MESSAGE_BROKER: "Брокер сообщений",
    }
    return {
        kind: C4ElementSpec(function=spec.function, technology=labels[kind])
        for kind, spec in DEFAULT_ELEMENT_SPECS.items()
    }
