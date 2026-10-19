from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from domain.exceptions.architecture_errors import (
    CyclicDependencyError,
    DisallowedConnectionTypeError,
    DuplicateNodeIdentifierError,
    IsolatedNodeError,
    NonExistentEdgeEndpointError,
)
from domain.models.enums import NodeType
from domain.models.topology import AnyNode, ArchitectureGraph
from domain.specifications.structural_validator import StructuralTopologyValidator
from tests.factories import create_test_edge, create_test_node

if TYPE_CHECKING:
    from domain.models.edges import Edge
    from domain.specifications.interfaces import ValidationResult

pytestmark = pytest.mark.unit


class TestStructuralTopologyValidator:
    """Test observable behavior and business rules of structural validation."""

    def test_should_pass_validation_when_topology_is_valid_dag(self) -> None:
        # Arrange
        client_node: AnyNode = create_test_node("client_1", NodeType.CLIENT)
        load_balancer_node: AnyNode = create_test_node("lb_1", NodeType.LOAD_BALANCER)
        compute_node: AnyNode = create_test_node("compute_1", NodeType.COMPUTE)
        database_node: AnyNode = create_test_node("db_1", NodeType.DATABASE)

        nodes: list[AnyNode] = [
            client_node,
            load_balancer_node,
            compute_node,
            database_node,
        ]
        edges: list[Edge] = [
            create_test_edge("client_1", "lb_1"),
            create_test_edge("lb_1", "compute_1"),
            create_test_edge("compute_1", "db_1"),
        ]
        graph: ArchitectureGraph = ArchitectureGraph(nodes=nodes, edges=edges)
        validator: StructuralTopologyValidator = StructuralTopologyValidator()

        # Act
        result: ValidationResult = validator.validate(graph)

        # Assert
        assert result.is_successful is True
        assert len(result.errors) == 0

    def test_should_fail_validation_when_duplicate_node_identifiers_exist(
        self,
    ) -> None:
        # Arrange
        node_original: AnyNode = create_test_node("duplicate_id", NodeType.COMPUTE)
        node_duplicate: AnyNode = create_test_node("duplicate_id", NodeType.COMPUTE)

        graph: ArchitectureGraph = ArchitectureGraph(
            nodes=[node_original, node_duplicate],
            edges=[],
        )
        validator: StructuralTopologyValidator = StructuralTopologyValidator()

        # Act
        result: ValidationResult = validator.validate(graph)

        # Assert
        assert result.is_successful is False
        assert result.has_error(DuplicateNodeIdentifierError)
        assert any(
            isinstance(error, DuplicateNodeIdentifierError)
            and "duplicate_id" in error.affected_node_identifiers
            for error in result.errors
        )

    def test_should_fail_validation_when_edge_points_to_non_existent_node(
        self,
    ) -> None:
        # Arrange
        existing_node: AnyNode = create_test_node("client_1", NodeType.CLIENT)
        invalid_edge: Edge = create_test_edge("client_1", "non_existent_server")

        graph: ArchitectureGraph = ArchitectureGraph(
            nodes=[existing_node],
            edges=[invalid_edge],
        )
        validator: StructuralTopologyValidator = StructuralTopologyValidator()

        # Act
        result: ValidationResult = validator.validate(graph)

        # Assert
        assert result.is_successful is False
        assert result.has_error(NonExistentEdgeEndpointError)
        assert any(
            isinstance(error, NonExistentEdgeEndpointError)
            and error.affected_edge == ("client_1", "non_existent_server")
            for error in result.errors
        )

    def test_should_fail_validation_when_connection_violates_architectural_rules(
        self,
    ) -> None:
        # Arrange: Direct Load Balancer -> Database connection is forbidden
        load_balancer_node: AnyNode = create_test_node("lb_1", NodeType.LOAD_BALANCER)
        database_node: AnyNode = create_test_node("db_1", NodeType.DATABASE)
        forbidden_edge: Edge = create_test_edge("lb_1", "db_1")

        graph: ArchitectureGraph = ArchitectureGraph(
            nodes=[load_balancer_node, database_node],
            edges=[forbidden_edge],
        )
        validator: StructuralTopologyValidator = StructuralTopologyValidator()

        # Act
        result: ValidationResult = validator.validate(graph)

        # Assert
        assert result.is_successful is False
        assert result.has_error(DisallowedConnectionTypeError)
        assert any(
            isinstance(error, DisallowedConnectionTypeError)
            and error.affected_edge == ("lb_1", "db_1")
            for error in result.errors
        )

    def test_should_fail_validation_when_topology_contains_cyclic_dependency(
        self,
    ) -> None:
        # Arrange: compute_1 -> compute_2 -> compute_1 (cycle)
        compute_node_1: AnyNode = create_test_node("compute_1", NodeType.COMPUTE)
        compute_node_2: AnyNode = create_test_node("compute_2", NodeType.COMPUTE)

        cycle_edges: list[Edge] = [
            create_test_edge("compute_1", "compute_2"),
            create_test_edge("compute_2", "compute_1"),
        ]
        graph: ArchitectureGraph = ArchitectureGraph(
            nodes=[compute_node_1, compute_node_2],
            edges=cycle_edges,
        )
        validator: StructuralTopologyValidator = StructuralTopologyValidator()

        # Act
        result: ValidationResult = validator.validate(graph)

        # Assert
        assert result.is_successful is False
        assert result.has_error(CyclicDependencyError)
        assert any(
            isinstance(error, CyclicDependencyError)
            and "compute_1" in error.affected_node_identifiers
            and "compute_2" in error.affected_node_identifiers
            for error in result.errors
        )

    def test_should_fail_validation_when_node_is_completely_isolated(
        self,
    ) -> None:
        # Arrange
        client_node: AnyNode = create_test_node("client_1", NodeType.CLIENT)
        compute_node: AnyNode = create_test_node("compute_1", NodeType.COMPUTE)
        isolated_database: AnyNode = create_test_node("db_orphan", NodeType.DATABASE)

        connected_edges: list[Edge] = [create_test_edge("client_1", "compute_1")]
        graph: ArchitectureGraph = ArchitectureGraph(
            nodes=[client_node, compute_node, isolated_database],
            edges=connected_edges,
        )
        validator: StructuralTopologyValidator = StructuralTopologyValidator()

        # Act
        result: ValidationResult = validator.validate(graph)

        # Assert
        assert result.is_successful is False
        assert result.has_error(IsolatedNodeError)
        assert any(
            isinstance(error, IsolatedNodeError)
            and "db_orphan" in error.affected_node_identifiers
            for error in result.errors
        )

    def test_should_pass_validation_when_graph_consists_of_single_node(
        self,
    ) -> None:
        # Arrange
        single_node: AnyNode = create_test_node("standalone_worker", NodeType.COMPUTE)
        graph: ArchitectureGraph = ArchitectureGraph(nodes=[single_node], edges=[])
        validator: StructuralTopologyValidator = StructuralTopologyValidator()

        # Act
        result: ValidationResult = validator.validate(graph)

        # Assert
        assert result.is_successful is True
        assert len(result.errors) == 0
