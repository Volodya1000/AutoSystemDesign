"""Typed factories for architecture topology tests."""

from typing import Any, TypedDict, Unpack

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


def _capacity_fields(replicas_count: int) -> dict[str, Any]:
    """Return required capacity attributes shared by compute-like node models."""
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
    replicas: int
    cost: float


def create_test_compute_node(
    identifier: str, **overrides: Unpack[_CapacityOverrides]
) -> ComputeNode:
    """Build a compute node with optional capacity values for focused tests."""
    field_names = {
        "concurrency": "maximum_concurrency",
        "mean_ms": "mean_processing_time_milliseconds",
        "std_ms": "standard_deviation_processing_time",
        "replicas": "replicas_count",
        "cost": "monthly_cost_usd",
    }
    capacity = _capacity_fields(replicas_count=1)
    capacity.update({field_names[name]: value for name, value in overrides.items()})
    return ComputeNode(identifier=identifier, **capacity)


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


def create_test_latency_graph() -> ArchitectureGraph:
    """Build a low-load graph whose mean response time exceeds a tiny p99 target."""
    return ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node(
                "service",
                concurrency=1,
                mean_ms=10.0,
                std_ms=10.0,
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
