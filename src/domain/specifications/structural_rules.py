from __future__ import annotations

from typing import TYPE_CHECKING

from domain.exceptions.architecture_errors import (
    ArchitectureValidationError,
    CyclicDependencyError,
    DisallowedConnectionTypeError,
    DuplicateNodeIdentifierError,
    IsolatedNodeError,
    NonExistentEdgeEndpointError,
)
from domain.specifications.rules import ConnectionType

if TYPE_CHECKING:
    from domain.models.nodes import BaseNode
    from domain.models.topology import ArchitectureGraph


def check_node_identifiers_uniqueness(
    graph: ArchitectureGraph,
) -> list[ArchitectureValidationError]:
    """Ensures all node identifiers within the topology graph are unique."""
    errors: list[ArchitectureValidationError] = []
    seen_identifiers: set[str] = set()

    for node in graph.nodes:
        if node.identifier in seen_identifiers:
            errors.append(DuplicateNodeIdentifierError(node_identifier=node.identifier))
        seen_identifiers.add(node.identifier)

    return errors


def check_edge_referential_integrity(
    graph: ArchitectureGraph,
) -> list[ArchitectureValidationError]:
    """Ensures all edges connect nodes that actually exist in the topology."""
    errors: list[ArchitectureValidationError] = []
    existing_identifiers: set[str] = {node.identifier for node in graph.nodes}

    for edge in graph.edges:
        missing_identifiers: list[str] = []
        if edge.source_identifier not in existing_identifiers:
            missing_identifiers.append(edge.source_identifier)
        if edge.target_identifier not in existing_identifiers:
            missing_identifiers.append(edge.target_identifier)

        if missing_identifiers:
            errors.append(
                NonExistentEdgeEndpointError(
                    missing_identifiers=missing_identifiers,
                    edge=(edge.source_identifier, edge.target_identifier),
                )
            )

    return errors


def check_connection_rules(
    graph: ArchitectureGraph,
    allowed_connection_types: frozenset[ConnectionType],
) -> list[ArchitectureValidationError]:
    """Validates that edge transitions strictly match the allowed architectural whitelist."""
    errors: list[ArchitectureValidationError] = []
    node_lookup: dict[str, BaseNode] = {node.identifier: node for node in graph.nodes}

    for edge in graph.edges:
        if (
            edge.source_identifier in node_lookup
            and edge.target_identifier in node_lookup
        ):
            source_node: BaseNode = node_lookup[edge.source_identifier]
            target_node: BaseNode = node_lookup[edge.target_identifier]
            transition: ConnectionType = ConnectionType(
                source=source_node.node_type,
                target=target_node.node_type,
            )

            if transition not in allowed_connection_types:
                errors.append(
                    DisallowedConnectionTypeError(
                        source_identifier=source_node.identifier,
                        source_type=source_node.node_type,
                        target_identifier=target_node.identifier,
                        target_type=target_node.node_type,
                    )
                )

    return errors


def check_isolated_nodes(
    graph: ArchitectureGraph,
) -> list[ArchitectureValidationError]:
    """Detects nodes with neither incoming nor outgoing connections in multi-node topologies."""
    if len(graph.nodes) <= 1:
        return []

    connected_identifiers: set[str] = set()
    for edge in graph.edges:
        connected_identifiers.add(edge.source_identifier)
        connected_identifiers.add(edge.target_identifier)

    return [
        IsolatedNodeError(node_identifier=node.identifier)
        for node in graph.nodes
        if node.identifier not in connected_identifiers
    ]


def check_acyclicity(
    graph: ArchitectureGraph,
) -> list[ArchitectureValidationError]:
    """Ensures the graph is a Directed Acyclic Graph (DAG) with no cyclic dependencies."""
    node_identifiers: list[str] = [node.identifier for node in graph.nodes]
    adjacency_list: dict[str, list[str]] = {
        identifier: [] for identifier in node_identifiers
    }
    for edge in graph.edges:
        if (
            edge.source_identifier in adjacency_list
            and edge.target_identifier in adjacency_list
        ):
            adjacency_list[edge.source_identifier].append(edge.target_identifier)

    # 0 = unvisited, 1 = visiting (in active recursion stack), 2 = visited
    visit_state: dict[str, int] = {identifier: 0 for identifier in node_identifiers}
    cycle_errors: list[ArchitectureValidationError] = []

    def depth_first_search(current_identifier: str, current_path: list[str]) -> None:
        visit_state[current_identifier] = 1
        current_path.append(current_identifier)

        for neighbor_identifier in adjacency_list[current_identifier]:
            if visit_state[neighbor_identifier] == 1:
                cycle_start_index: int = current_path.index(neighbor_identifier)
                cycle_sequence: list[str] = current_path[cycle_start_index:] + [
                    neighbor_identifier
                ]
                cycle_errors.append(
                    CyclicDependencyError(cycle_sequence=cycle_sequence)
                )
            elif visit_state[neighbor_identifier] == 0:
                depth_first_search(neighbor_identifier, current_path)

        current_path.pop()
        visit_state[current_identifier] = 2

    for identifier in node_identifiers:
        if visit_state[identifier] == 0:
            depth_first_search(identifier, [])

    return cycle_errors
