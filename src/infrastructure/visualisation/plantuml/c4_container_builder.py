"""Rendering of an ArchitectureGraph into a PlantUML C4 Container diagram.

The builder is pure: no I/O, no network, no clock. Element specs and
alias assignment live in dedicated modules; this one only decides how
the document is assembled from graph elements (SRP).
"""

from collections.abc import Mapping
from typing import Final

from domain.models.edges import Edge
from domain.models.enums import NodeType
from domain.models.nodes import (
    CacheNode,
    CapacityNode,
    DatabaseNode,
    MessageBrokerNode,
)
from domain.models.protocols import ConnectionProtocol
from domain.models.topology import AnyNode, ArchitectureGraph
from infrastructure.visualisation.plantuml.aliases import AliasRegistry
from infrastructure.visualisation.plantuml.diagram_registry import (
    register_diagram_builder,
)
from infrastructure.visualisation.plantuml.element_specs import (
    DEFAULT_ELEMENT_SPECS,
    C4ElementSpec,
)
from infrastructure.visualisation.plantuml.ports import DiagramSourceBuilder

C4_STDLIB_BUNDLED_INCLUDE: Final[str] = "<C4/C4_Container>"
C4_STDLIB_REMOTE_INCLUDE_URL: Final[str] = (
    "https://raw.githubusercontent.com/plantuml-stdlib/C4-PlantUML/master/"
    "C4_Container.puml"
)

_SYSTEM_BOUNDARY_ALIAS: Final[str] = "system_boundary"


@register_diagram_builder("c4")
def _c4_builder_factory() -> DiagramSourceBuilder:
    return C4ContainerDiagramBuilder()


def _quote(text: str) -> str:
    """Escapes a value for use in a PlantUML double-quoted string."""
    escaped: str = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "")
        .replace("\n", "\\n")
    )
    return f'"{escaped}"'


def _node_type_facts(node: CapacityNode) -> list[str]:
    """Collects node-type-specific facts for an element description."""
    match node:
        case DatabaseNode():
            facts: list[str] = [
                f"role={node.database_role.value}",
                f"shards={node.shards_count}",
            ]
            if node.input_output_operations_per_second_limit is not None:
                facts.append(
                    f"iops_limit={node.input_output_operations_per_second_limit}"
                )
            return facts
        case CacheNode():
            return [f"hit_rate={node.cache_hit_rate_probability:.0%}"]
        case MessageBrokerNode():
            if node.retention_period_hours is None:
                return []
            return [f"retention={node.retention_period_hours}h"]
        case _:
            return []


def _describe_node(node: AnyNode) -> str:
    """Builds a compact description shown under the element label."""
    if not isinstance(node, CapacityNode):
        return "external traffic source"
    facts: list[str] = [
        f"replicas={node.replicas_count}",
        f"concurrency={node.maximum_concurrency}",
        f"mean={node.mean_processing_time_milliseconds:g} ms",
        f"cost=${node.monthly_cost_usd:g}/mo",
    ]
    facts.extend(_node_type_facts(node))
    return ", ".join(facts)


def _edge_label(protocol: ConnectionProtocol) -> str:
    """Rel label: the protocol name plus an async marker when needed."""
    if protocol.is_asynchronous and "async" not in protocol.name.lower():
        return f"{protocol.name} (async)"
    return protocol.name


def _edge_technology(edge: Edge) -> str:
    """Rel technology line: edge description plus network latency."""
    latency: str = f"{edge.network_latency_milliseconds:g} ms network"
    description: str = edge.description.strip()
    if not description:
        return latency
    return f"{description} - {latency}"


def _format_element(spec: C4ElementSpec, alias: str, node: AnyNode) -> str:
    """Formats a single C4 element call."""
    arguments: list[str] = [alias, _quote(node.identifier)]
    if spec.technology:
        arguments.append(_quote(spec.technology))
    arguments.append(_quote(_describe_node(node)))
    return f"{spec.function}({', '.join(arguments)})"


def _format_relation(edge: Edge, aliases: AliasRegistry) -> str | None:
    """Formats a single Rel call; returns None for a dangling endpoint.

    Graphs that failed structural validation can reference unknown node
    identifiers; such edges are skipped so the diagram still renders.
    """
    source_alias: str | None = aliases.find(edge.source_identifier)
    target_alias: str | None = aliases.find(edge.target_identifier)
    if source_alias is None or target_alias is None:
        return None
    arguments: list[str] = [
        source_alias,
        target_alias,
        _quote(_edge_label(edge.protocol)),
        _quote(_edge_technology(edge)),
    ]
    return f"Rel({', '.join(arguments)})"


class C4ContainerDiagramBuilder:
    """Builds the .puml source of a C4 Container (Level 2) diagram.

    The default include uses the C4 standard library bundled into every
    PlantUML distribution, so the document renders on the public
    server, on Kroki and on a local jar without extra network hops. Use
    C4_STDLIB_REMOTE_INCLUDE_URL to always track the master version of
    the library instead.
    """

    def __init__(
        self,
        element_specs: Mapping[NodeType, C4ElementSpec] | None = None,
        c4_include: str = C4_STDLIB_BUNDLED_INCLUDE,
        system_boundary_label: str = "System",
        show_legend: bool = True,
    ) -> None:
        merged_specs: dict[NodeType, C4ElementSpec] = dict(DEFAULT_ELEMENT_SPECS)
        if element_specs is not None:
            merged_specs.update(element_specs)
        self._element_specs: dict[NodeType, C4ElementSpec] = merged_specs
        self._c4_include: str = c4_include
        self._system_boundary_label: str = system_boundary_label
        self._show_legend: bool = show_legend

    def build(self, graph: ArchitectureGraph, title: str | None = None) -> str:
        """Returns the complete PlantUML document for the graph."""
        aliases: AliasRegistry = AliasRegistry(reserved={_SYSTEM_BOUNDARY_ALIAS})
        external_elements: list[str] = []
        internal_elements: list[str] = []
        node: AnyNode
        for node in graph.nodes:
            spec: C4ElementSpec = self._element_specs.get(
                node.node_type,
                C4ElementSpec(function="Container", technology=node.node_type.value),
            )
            alias: str = aliases.register(node.identifier)
            element: str = _format_element(spec, alias, node)
            if node.node_type is NodeType.CLIENT:
                external_elements.append(element)
            else:
                internal_elements.append(element)
        relations: list[str] = []
        edge: Edge
        for edge in graph.edges:
            relation: str | None = _format_relation(edge, aliases)
            if relation is not None:
                relations.append(relation)
        return self._assemble_document(
            title=title,
            external_elements=external_elements,
            internal_elements=internal_elements,
            relations=relations,
        )

    def _assemble_document(
        self,
        title: str | None,
        external_elements: list[str],
        internal_elements: list[str],
        relations: list[str],
    ) -> str:
        """Joins diagram parts into the final PlantUML document text."""
        lines: list[str] = [
            "@startuml",
            f"!include {self._c4_include}",
            "",
        ]
        if title:
            lines.append("title")
            lines.extend(title.split("\n"))
            lines.append("end title")
            lines.append("")
        if external_elements:
            lines.extend([*external_elements, ""])
        if internal_elements:
            boundary_header: str = (
                f"System_Boundary({_SYSTEM_BOUNDARY_ALIAS}, "
                f"{_quote(self._system_boundary_label)}) {{"
            )
            lines.append(boundary_header)
            lines.extend(f"    {element}" for element in internal_elements)
            lines.extend(["}", ""])
        if relations:
            lines.extend([*relations, ""])
        if self._show_legend:
            lines.append("SHOW_LEGEND()")
        lines.append("@enduml")
        return "\n".join(lines) + "\n"
