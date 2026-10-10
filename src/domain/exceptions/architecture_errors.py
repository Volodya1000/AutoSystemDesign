from domain.models.enums import NodeType


class ArchitectureValidationError(Exception):
    """Base exception for all architectural topology and constraint violations."""

    error_code: str = "GENERIC_ARCHITECTURE_ERROR"

    def __init__(
        self,
        message: str,
        affected_node_identifiers: list[str] | None = None,
        affected_edge: tuple[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message: str = message
        self.affected_node_identifiers: list[str] = affected_node_identifiers or []
        self.affected_edge: tuple[str, str] | None = affected_edge


class DuplicateNodeIdentifierError(ArchitectureValidationError):
    error_code: str = "DUPLICATE_NODE_IDENTIFIER"

    def __init__(self, node_identifier: str) -> None:
        message: str = (
            f"Node identifier '{node_identifier}' is duplicated in the topology."
        )
        super().__init__(message=message, affected_node_identifiers=[node_identifier])


class NonExistentEdgeEndpointError(ArchitectureValidationError):
    error_code: str = "NON_EXISTENT_EDGE_ENDPOINT"

    def __init__(self, missing_identifiers: list[str], edge: tuple[str, str]) -> None:
        message: str = (
            f"Edge references non-existent node identifiers: {missing_identifiers}."
        )
        super().__init__(
            message=message,
            affected_node_identifiers=missing_identifiers,
            affected_edge=edge,
        )


class DisallowedConnectionTypeError(ArchitectureValidationError):
    error_code: str = "DISALLOWED_CONNECTION_TYPE"

    def __init__(
        self,
        source_identifier: str,
        source_type: NodeType,
        target_identifier: str,
        target_type: NodeType,
    ) -> None:
        message: str = (
            f"Direct connection from '{source_type}' to '{target_type}' "
            f"is prohibited by architectural rules."
        )
        super().__init__(
            message=message,
            affected_node_identifiers=[source_identifier, target_identifier],
            affected_edge=(source_identifier, target_identifier),
        )


class CyclicDependencyError(ArchitectureValidationError):
    error_code: str = "CYCLIC_DEPENDENCY_DETECTED"

    def __init__(self, cycle_sequence: list[str]) -> None:
        message: str = f"Cyclic dependency detected: {' -> '.join(cycle_sequence)}."
        super().__init__(message=message, affected_node_identifiers=cycle_sequence)


class IsolatedNodeError(ArchitectureValidationError):
    error_code: str = "ISOLATED_NODE"

    def __init__(self, node_identifier: str) -> None:
        message: str = (
            f"Node '{node_identifier}' is isolated with no "
            f"incoming or outgoing connections."
        )
        super().__init__(message=message, affected_node_identifiers=[node_identifier])


class CapacitySaturationError(ArchitectureValidationError):
    error_code: str = "CAPACITY_SATURATION_ERROR"

    def __init__(
        self,
        node_identifier: str,
        utilization_percentage: float,
        arrival_rate_rps: float,
        maximum_capacity_rps: float,
    ) -> None:
        message: str = (
            f"Node '{node_identifier}' is mathematically saturated. "
            f"Utilization: {utilization_percentage:.1f}%. "
            f"Incoming traffic ({arrival_rate_rps:.1f} RPS) exceeds "
            f"maximum processing capacity ({maximum_capacity_rps:.1f} RPS)."
        )
        super().__init__(message=message, affected_node_identifiers=[node_identifier])


class TheoreticalLatencyViolationError(ArchitectureValidationError):
    error_code: str = "THEORETICAL_LATENCY_VIOLATION"

    def __init__(
        self,
        critical_path_node_identifiers: list[str],
        calculated_mean_latency_milliseconds: float,
        target_threshold_milliseconds: float,
    ) -> None:
        message: str = (
            f"Theoretical mean latency along critical path "
            f"({calculated_mean_latency_milliseconds:.2f} ms) exceeds "
            f"target SLA threshold ({target_threshold_milliseconds:.2f} ms). "
            f"Critical path: {' -> '.join(critical_path_node_identifiers)}."
        )
        super().__init__(
            message=message,
            affected_node_identifiers=critical_path_node_identifiers,
        )
