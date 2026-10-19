from __future__ import annotations

from typing import TYPE_CHECKING

from domain.specifications.interfaces import BaseValidator, ValidationResult
from domain.specifications.rules import DEFAULT_ALLOWED_CONNECTION_TYPES, ConnectionType
from domain.specifications.structural_rules import (
    check_acyclicity,
    check_connection_rules,
    check_edge_referential_integrity,
    check_isolated_nodes,
    check_node_identifiers_uniqueness,
)

if TYPE_CHECKING:
    from domain.exceptions.architecture_errors import ArchitectureValidationError
    from domain.models.topology import ArchitectureGraph


class StructuralTopologyValidator(BaseValidator):
    """Orchestrates pure structural validation of DAG topology.

    Checks referential consistency and connection whitelist compliance.
    """

    def __init__(
        self,
        allowed_connection_types: frozenset[ConnectionType] | None = None,
    ) -> None:
        self._allowed_connection_types: frozenset[ConnectionType] = (
            frozenset(allowed_connection_types)
            if allowed_connection_types is not None
            else DEFAULT_ALLOWED_CONNECTION_TYPES
        )

    def validate(self, graph: ArchitectureGraph) -> ValidationResult:
        collected_errors: list[ArchitectureValidationError] = [
            *check_node_identifiers_uniqueness(graph),
            *check_edge_referential_integrity(graph),
            *check_connection_rules(graph, self._allowed_connection_types),
            *check_acyclicity(graph),
            *check_isolated_nodes(graph),
        ]

        return ValidationResult(errors=collected_errors)
