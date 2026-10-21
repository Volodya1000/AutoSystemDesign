"""Mapping of domain node types onto C4-PlantUML element calls.

Kept apart from the builder so the presentation table can evolve (new
node types, other element choices) independently of the document
assembly logic.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from domain.models.enums import NodeType


@dataclass(frozen=True)
class C4ElementSpec:
    """C4-PlantUML element call used for one domain node type.

    An empty `technology` omits the technology argument: Person calls
    have no technology parameter, Container-family calls do.
    """

    function: str
    technology: str = ""


DEFAULT_ELEMENT_SPECS: Final[Mapping[NodeType, C4ElementSpec]] = MappingProxyType({
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
})
