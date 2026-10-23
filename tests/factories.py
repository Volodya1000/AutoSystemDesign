"""Typed factories for architecture topology tests."""

from typing import TypedDict, Unpack

from domain.models.edges import Edge
from domain.models.enums import EdgeRoutingMode, NodeType
from domain.models.nodes import (
    CacheNode,
    ClientNode,
    ComputeNode,
    DatabaseNode,
    LoadBalancerNode,
    MessageBrokerNode,
)
from domain.models.protocols import SYNCHRONOUS_REST_HTTP
from domain.models.requirements import LatencyRequirement
from domain.models.scenarios import DesignScenario, WorkloadProfile
from domain.models.topology import AnyNode, ArchitectureGraph
from domain.service_profiles import ServiceProfile


class _CapacityFields(TypedDict):
    """Typed shared capacity defaults used by test node factories."""

    replicas_count: int
    maximum_concurrency: int
    maximum_queue_size: int
    mean_processing_time_milliseconds: float
    standard_deviation_processing_time: float
    monthly_cost_usd: float


def _capacity_fields(replicas_count: int) -> _CapacityFields:
    """Return strictly typed defaults for compute-like test nodes."""
    return {
        "replicas_count": replicas_count,
        "maximum_concurrency": 100,
        "maximum_queue_size": 500,
        "mean_processing_time_milliseconds": 10.0,
        "standard_deviation_processing_time": 2.0,
        "monthly_cost_usd": 50.0,
    }


class _CapacityOverrides(TypedDict, total=False):
    concurrency: int
    mean_ms: float
    std_ms: float
    service_channels_per_replica: int | None
    queue_size: int
    replicas: int
    cost: float


def create_test_compute_node(
    identifier: str, **overrides: Unpack[_CapacityOverrides]
) -> ComputeNode:
    """Build a compute node with optional capacity values for focused tests."""
    defaults = _capacity_fields(replicas_count=1)
    return ComputeNode(
        identifier=identifier,
        replicas_count=overrides.get("replicas", defaults["replicas_count"]),
        maximum_concurrency=overrides.get(
            "concurrency", defaults["maximum_concurrency"]
        ),
        maximum_queue_size=overrides.get("queue_size", defaults["maximum_queue_size"]),
        service_channels_per_replica=overrides.get("service_channels_per_replica"),
        mean_processing_time_milliseconds=overrides.get(
            "mean_ms", defaults["mean_processing_time_milliseconds"]
        ),
        standard_deviation_processing_time=overrides.get(
            "std_ms", defaults["standard_deviation_processing_time"]
        ),
        monthly_cost_usd=overrides.get("cost", defaults["monthly_cost_usd"]),
    )


class UnsupportedTestNodeTypeError(ValueError):
    """Unsupported node type requested by a test factory."""

    def __init__(self, node_type: object) -> None:
        super().__init__(f"Unsupported node type in tests: {node_type}")


def create_test_node(
    identifier: str,
    node_type: NodeType,
    replicas_count: int = 1,
    cache_hit_rate_probability: float = 0.8,
) -> AnyNode:
    """Build the registered node model for a given type and identifier."""
    match node_type:
        case NodeType.CLIENT:
            return ClientNode(identifier=identifier, replicas_count=replicas_count)
        case NodeType.LOAD_BALANCER:
            return LoadBalancerNode(
                identifier=identifier, **_capacity_fields(replicas_count)
            )
        case NodeType.COMPUTE:
            return ComputeNode(
                identifier=identifier, **_capacity_fields(replicas_count)
            )
        case NodeType.DATABASE:
            return DatabaseNode(
                identifier=identifier, **_capacity_fields(replicas_count)
            )
        case NodeType.CACHE:
            return CacheNode(
                identifier=identifier,
                **_capacity_fields(replicas_count),
                cache_hit_rate_probability=cache_hit_rate_probability,
            )
        case NodeType.MESSAGE_BROKER:
            return MessageBrokerNode(
                identifier=identifier, **_capacity_fields(replicas_count)
            )
        case _:
            raise UnsupportedTestNodeTypeError(node_type)


def create_test_edge(
    source_identifier: str,
    target_identifier: str,
    *,
    routing_mode: EdgeRoutingMode = EdgeRoutingMode.ALTERNATIVE,
) -> Edge:
    """Create a deterministic synchronous edge between topology nodes."""
    return Edge(
        source_identifier=source_identifier,
        target_identifier=target_identifier,
        protocol=SYNCHRONOUS_REST_HTTP,
        routing_mode=routing_mode,
        network_latency_milliseconds=1.0,
    )


def create_test_latency_graph(
    *,
    service_channels_per_replica: int | None = None,
    concurrency: int = 1,
    queue_size: int = 500,
) -> ArchitectureGraph:
    """Build a low-load graph whose mean response time exceeds a tiny p99 target."""
    return ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node(
                "service",
                concurrency=concurrency,
                mean_ms=10.0,
                std_ms=10.0,
                service_channels_per_replica=service_channels_per_replica,
                queue_size=queue_size,
            ),
        ],
        edges=[create_test_edge("client", "service")],
    )


def create_test_latency_scenario() -> DesignScenario:
    """Build a stable workload with a percentile target unsupported by the model."""
    return DesignScenario(
        identifier="latency_slo_test",
        description="A percentile target that the current model cannot evaluate",
        workload=WorkloadProfile(
            baseline_requests_per_second=10.0,
            peak_requests_per_second=20.0,
        ),
        requirements=[LatencyRequirement(threshold_value=1.0, percentile=99.0)],
    )


def create_test_service_profile() -> ServiceProfile:
    """Build an explicitly sourced, stable synthetic processing profile."""
    return ServiceProfile(
        source="Explicit synthetic test assumption",
        provenance="assumption",
        replicas_count=1,
        maximum_concurrency=8,
        maximum_queue_size=100,
        service_channels_per_replica=2,
        mean_processing_time_milliseconds=10,
        standard_deviation_processing_time=5,
        monthly_cost_usd=50,
    )
