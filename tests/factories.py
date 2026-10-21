# Copyright (c) 2026 Volodya1000
"""Typed factories for architecture topology tests."""

from typing import Any, TypedDict, Unpack

from domain.models.edges import Edge
from domain.models.enums import NodeType
from domain.models.nodes import (
    CacheNode,
    ClientNode,
    ComputeNode,
    DatabaseNode,
    LoadBalancerNode,
    MessageBrokerNode,
)
from domain.models.protocols import SYNCHRONOUS_REST_HTTP
from domain.models.topology import AnyNode


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
            return CacheNode(identifier=identifier, **_capacity_fields(replicas_count))
        case NodeType.MESSAGE_BROKER:
            return MessageBrokerNode(
                identifier=identifier, **_capacity_fields(replicas_count)
            )
        case _:
            raise UnsupportedTestNodeTypeError(node_type)


def create_test_edge(
    source_identifier: str,
    target_identifier: str,
) -> Edge:
    """Create a deterministic synchronous edge between topology nodes."""
    return Edge(
        source_identifier=source_identifier,
        target_identifier=target_identifier,
        protocol=SYNCHRONOUS_REST_HTTP,
        network_latency_milliseconds=1.0,
    )
