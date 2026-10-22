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


class BudgetExceededError(ArchitectureValidationError):
    error_code: str = "BUDGET_EXCEEDED"

    def __init__(
        self,
        total_monthly_cost_usd: float,
        budget_limit_usd: float,
    ) -> None:
        message: str = (
            f"Total monthly cost ${total_monthly_cost_usd:.2f} exceeds "
            f"budget limit ${budget_limit_usd:.2f}."
        )
        super().__init__(message=message)
        self.total_monthly_cost_usd: float = total_monthly_cost_usd
        self.budget_limit_usd: float = budget_limit_usd


class DuplicateOperationIdError(ArchitectureValidationError):
    error_code: str = "DUPLICATE_OPERATION_ID"

    def __init__(self, operation_id: str) -> None:
        message: str = (
            f"Operation ID '{operation_id}' is duplicated across the API design."
        )
        super().__init__(message=message)
        self.operation_id: str = operation_id


class PathCollisionError(ArchitectureValidationError):
    error_code: str = "PATH_COLLISION_DETECTED"

    def __init__(self, method: str, path: str, normalized_path: str) -> None:
        message: str = (
            f"Path collision detected: method '{method.upper()}' with path '{path}' "
            f"collides with another endpoint normalizing to '{normalized_path}'."
        )
        super().__init__(message=message)
        self.method: str = method
        self.path: str = path
        self.normalized_path: str = normalized_path


class MissingPathParameterError(ArchitectureValidationError):
    error_code: str = "MISSING_PATH_PARAMETER"

    def __init__(self, operation_id: str, missing_parameters: list[str]) -> None:
        message: str = (
            f"Operation '{operation_id}' defines URL path variables "
            f"{sorted(missing_parameters)} that are missing from the declared "
            "parameters list with in='path'."
        )
        super().__init__(message=message)
        self.operation_id: str = operation_id
        self.missing_parameters: list[str] = missing_parameters


class UndeclaredPathParameterError(ArchitectureValidationError):
    error_code: str = "UNDECLARED_PATH_PARAMETER"

    def __init__(self, operation_id: str, undeclared_parameters: list[str]) -> None:
        message: str = (
            f"Operation '{operation_id}' declares path parameters "
            f"{sorted(undeclared_parameters)} that do not exist in the URL "
            "path template."
        )
        super().__init__(message=message)
        self.operation_id: str = operation_id
        self.undeclared_parameters: list[str] = undeclared_parameters


class UnresolvedSchemaReferenceError(ArchitectureValidationError):
    error_code: str = "UNRESOLVED_SCHEMA_REFERENCE"

    def __init__(self, operation_id: str, target: str, missing_schema_ref: str) -> None:
        message: str = (
            f"Operation '{operation_id}' ({target}) references unknown schema "
            f"'{missing_schema_ref}', which is not registered in central schemas."
        )
        super().__init__(message=message)
        self.operation_id: str = operation_id
        self.target: str = target
        self.missing_schema_ref: str = missing_schema_ref


class NonExistentComponentReferenceError(ArchitectureValidationError):
    error_code: str = "NON_EXISTENT_COMPONENT_REFERENCE"

    def __init__(self, operation_id: str, role: str, component_id: str) -> None:
        message: str = (
            f"Operation '{operation_id}' {role} references component '{component_id}', "
            "which does not exist in the C4 architecture graph."
        )
        super().__init__(
            message=message,
            affected_node_identifiers=[component_id],
        )
        self.operation_id: str = operation_id
        self.role: str = role
        self.component_id: str = component_id


class NonExistentRequirementReferenceError(ArchitectureValidationError):
    error_code: str = "NON_EXISTENT_REQUIREMENT_REFERENCE"

    def __init__(self, operation_id: str, requirement_id: str) -> None:
        message: str = (
            f"Operation '{operation_id}' references unknown requirement "
            f"'{requirement_id}', which is not declared in scenario functional "
            "requirements."
        )
        super().__init__(message=message)
        self.operation_id: str = operation_id
        self.requirement_id: str = requirement_id


class MessageBrokerWithoutConsumerError(ArchitectureValidationError):
    error_code: str = "MESSAGE_BROKER_WITHOUT_CONSUMER"

    def __init__(self, broker_identifier: str) -> None:
        message: str = (
            f"Message broker '{broker_identifier}' has no consumer: add an "
            f"outgoing edge to a compute node (async consumer), or remove "
            f"the broker."
        )
        super().__init__(
            message=message,
            affected_node_identifiers=[broker_identifier],
        )


class MessageBrokerWithoutProducerError(ArchitectureValidationError):
    error_code: str = "MESSAGE_BROKER_WITHOUT_PRODUCER"

    def __init__(self, broker_identifier: str) -> None:
        message: str = (
            f"Message broker '{broker_identifier}' has no producer: add an "
            f"incoming edge from a compute node (async producer), or remove "
            f"the broker."
        )
        super().__init__(
            message=message,
            affected_node_identifiers=[broker_identifier],
        )


class MessageBrokerSelfLoopError(ArchitectureValidationError):
    error_code: str = "MESSAGE_BROKER_SELF_LOOP"

    def __init__(
        self,
        broker_identifier: str,
        compute_identifiers: list[str],
    ) -> None:
        nodes: str = ", ".join(f"'{identifier}'" for identifier in compute_identifiers)
        message: str = (
            f"Message broker '{broker_identifier}' routes messages from "
            f"compute node(s) {nodes} back to the same node(s). A broker "
            f"must bridge two DIFFERENT compute nodes: the producer "
            f"publishes to the broker, and a separate worker consumes from "
            f"it. Add a dedicated worker compute node behind the broker, "
            f"or remove the broker entirely."
        )
        super().__init__(
            message=message,
            affected_node_identifiers=[broker_identifier, *compute_identifiers],
        )


class CacheWriteOnlySinkError(ArchitectureValidationError):
    error_code: str = "CACHE_WRITE_ONLY_SINK"

    def __init__(
        self,
        cache_identifier: str,
        incoming_source_identifiers: list[str],
    ) -> None:
        sources: str = ", ".join(
            f"'{identifier}'" for identifier in incoming_source_identifiers
        )
        source_details: str = f" from {sources}" if sources else ""
        message: str = (
            f"Cache '{cache_identifier}' is a write-only or unread cache: "
            f"it has no synchronous incoming read edge{source_details}. "
            "Incoming edges are asynchronous writes or absent, so its "
            "cache_hit_rate is not realized. Add a synchronous read edge "
            "(compute -> cache), or remove the cache."
        )
        super().__init__(
            message=message,
            affected_node_identifiers=[cache_identifier],
        )


class AmbiguousCacheMissPathError(ArchitectureValidationError):
    error_code: str = "AMBIGUOUS_CACHE_MISS_PATH"

    def __init__(
        self,
        compute_identifier: str,
        cache_identifiers: list[str],
    ) -> None:
        caches = ", ".join(f"'{identifier}'" for identifier in cache_identifiers)
        message = (
            f"Compute node '{compute_identifier}' reads from multiple caches "
            f"({caches}), so its database miss traffic is ambiguous. Use one "
            "cache per compute reader or introduce an explicit cache-to-fallback "
            "mapping."
        )
        super().__init__(
            message=message,
            affected_node_identifiers=[compute_identifier, *cache_identifiers],
        )


class CacheMissPathMissingError(ArchitectureValidationError):
    error_code: str = "CACHE_MISS_PATH_MISSING"

    def __init__(
        self,
        cache_identifier: str,
        compute_identifier: str,
    ) -> None:
        message: str = (
            f"Cache '{cache_identifier}' has a synchronous read from compute "
            f"node '{compute_identifier}', but that compute node has no "
            "synchronous outgoing edge to a database for cache misses. Add a "
            f"'{compute_identifier} -> database' fallback edge, or remove the cache."
        )
        super().__init__(
            message=message,
            affected_node_identifiers=[cache_identifier, compute_identifier],
        )
