"""Unit tests of CacheUsageValidator.

Covers the write-only sink (the exact pattern the live run produced), the
broken miss path, the correct read+fallback pattern, multiple caches,
mixed sync/async incoming, and the scope boundaries (fully isolated
cache belongs to StructuralTopologyValidator).
"""

from __future__ import annotations

import pytest

from domain.exceptions.architecture_errors import (
    CacheMissPathMissingError,
    CacheWriteOnlySinkError,
)
from domain.models.edges import Edge
from domain.models.enums import NodeType
from domain.models.nodes import CacheNode, ComputeNode, DatabaseNode
from domain.models.protocols import (
    ConnectionProtocol,
    ASYNCHRONOUS_MESSAGE_QUEUE,
    SYNCHRONOUS_DATABASE_TCP,
    SYNCHRONOUS_GRPC,
    SYNCHRONOUS_REST_HTTP,
)
from domain.models.topology import AnyNode, ArchitectureGraph
from domain.specifications.cache_usage_validator import (
    CacheUsageValidator,
)
from domain.specifications.structural_validator import StructuralTopologyValidator
from tests.unit.test_structural_validator import (
    create_test_node,
)

pytestmark = pytest.mark.unit


# ------------------------------------------------------------------ helpers


def _cache(
    identifier: str,
    *,
    hit_rate: float = 0.8,
) -> CacheNode:
    return CacheNode(
        identifier=identifier,
        maximum_concurrency=500,
        maximum_queue_size=3_000,
        mean_processing_time_milliseconds=2.0,
        standard_deviation_processing_time=0.8,
        monthly_cost_usd=40.0,
        cache_hit_rate_probability=hit_rate,
    )


def _compute(identifier: str) -> ComputeNode:
    return ComputeNode(
        identifier=identifier,
        maximum_concurrency=400,
        maximum_queue_size=2_000,
        mean_processing_time_milliseconds=10.0,
        standard_deviation_processing_time=2.0,
        monthly_cost_usd=100.0,
    )


def _db(identifier: str) -> DatabaseNode:
    return DatabaseNode(
        identifier=identifier,
        maximum_concurrency=200,
        maximum_queue_size=1_000,
        mean_processing_time_milliseconds=5.0,
        standard_deviation_processing_time=1.0,
        monthly_cost_usd=70.0,
    )


def _edge(
    source: str,
    target: str,
    protocol: ConnectionProtocol,
) -> Edge:
    return Edge(
        source_identifier=source,
        target_identifier=target,
        protocol=protocol,
        network_latency_milliseconds=1.0,
    )


def _graph(*nodes: AnyNode, edges: list[Edge]) -> ArchitectureGraph:
    return ArchitectureGraph(nodes=list(nodes), edges=edges)


# ------------------------------------------------------------ happy path


class TestCacheWithReadAndFallback:
    def test_sync_read_and_compute_fallback_is_accepted(self) -> None:
        """Canonical pattern: compute reads cache, misses go to database."""
        graph = _graph(
            create_test_node("client", NodeType.CLIENT),
            _compute("processor"),
            _cache("message_cache"),
            _db("message_db"),
            edges=[
                _edge("client", "processor", SYNCHRONOUS_REST_HTTP),
                _edge("processor", "message_cache", SYNCHRONOUS_GRPC),
                _edge("processor", "message_db", SYNCHRONOUS_DATABASE_TCP),
            ],
        )

        result = CacheUsageValidator().validate(graph)

        assert result.is_successful is True
        assert result.errors == []

    def test_mixed_sync_and_async_incoming_is_accepted(self) -> None:
        """Read-through plus write-behind: both edges present, no error."""
        graph = _graph(
            create_test_node("client", NodeType.CLIENT),
            _compute("processor"),
            _cache("message_cache"),
            _db("message_db"),
            edges=[
                _edge("client", "processor", SYNCHRONOUS_REST_HTTP),
                _edge("processor", "message_cache", SYNCHRONOUS_GRPC),
                _edge("processor", "message_cache", ASYNCHRONOUS_MESSAGE_QUEUE),
                _edge("processor", "message_db", SYNCHRONOUS_DATABASE_TCP),
            ],
        )

        result = CacheUsageValidator().validate(graph)

        assert result.is_successful is True


# -------------------------------------------------------- write-only sink


class TestWriteOnlySink:
    def test_async_only_incoming_is_rejected(self) -> None:
        """Exactly the live-run defect: processor -> cache (async), nothing else."""
        graph = _graph(
            create_test_node("client", NodeType.CLIENT),
            _compute("processor"),
            _cache("message_cache"),
            edges=[
                _edge("client", "processor", SYNCHRONOUS_REST_HTTP),
                _edge("processor", "message_cache", ASYNCHRONOUS_MESSAGE_QUEUE),
            ],
        )

        result = CacheUsageValidator().validate(graph)

        assert result.is_successful is False
        errors = [e for e in result.errors if isinstance(e, CacheWriteOnlySinkError)]
        assert len(errors) == 1
        error = errors[0]
        assert error.affected_node_identifiers == ["message_cache"]
        assert "message_cache" in error.message
        assert "write-only" in error.message
        assert "'processor'" in error.message
        assert "cache_hit_rate" in error.message

    def test_write_only_sink_does_not_also_report_miss_path(self) -> None:
        """Mutual exclusion: write-only takes precedence."""
        graph = _graph(
            create_test_node("client", NodeType.CLIENT),
            _compute("processor"),
            _cache("message_cache"),
            edges=[
                _edge("client", "processor", SYNCHRONOUS_REST_HTTP),
                _edge("processor", "message_cache", ASYNCHRONOUS_MESSAGE_QUEUE),
            ],
        )

        result = CacheUsageValidator().validate(graph)

        assert not any(isinstance(e, CacheMissPathMissingError) for e in result.errors)


# ------------------------------------------------------ miss path missing


class TestMissPathMissing:
    def test_sync_read_without_fallback_is_rejected(self) -> None:
        """Compute reads cache, but its only outgoing edge IS the cache edge."""
        graph = _graph(
            create_test_node("client", NodeType.CLIENT),
            _compute("processor"),
            _cache("message_cache"),
            edges=[
                _edge("client", "processor", SYNCHRONOUS_REST_HTTP),
                _edge("processor", "message_cache", SYNCHRONOUS_GRPC),
            ],
        )

        result = CacheUsageValidator().validate(graph)

        assert result.is_successful is False
        errors = [e for e in result.errors if isinstance(e, CacheMissPathMissingError)]
        assert len(errors) == 1
        error = errors[0]
        assert error.affected_node_identifiers == ["message_cache", "processor"]
        assert "message_cache" in error.message
        assert "processor" in error.message
        assert "miss" in error.message.lower()

    def test_only_non_cache_outgoing_counts_as_fallback(self) -> None:
        """A second edge to the SAME cache is not a fallback."""
        graph = _graph(
            create_test_node("client", NodeType.CLIENT),
            _compute("processor"),
            _cache("message_cache"),
            edges=[
                _edge("client", "processor", SYNCHRONOUS_REST_HTTP),
                _edge("processor", "message_cache", SYNCHRONOUS_GRPC),
                _edge("processor", "message_cache", ASYNCHRONOUS_MESSAGE_QUEUE),
            ],
        )

        result = CacheUsageValidator().validate(graph)

        assert result.is_successful is False
        assert any(isinstance(e, CacheMissPathMissingError) for e in result.errors)


# -------------------------------------------------- multiple sync readers


class TestMultipleSyncReaders:
    def test_only_compute_without_fallback_is_reported(self) -> None:
        """Two compute nodes read the same cache; one has a DB fallback,
        the other does not. Only the second must be reported."""
        graph = _graph(
            create_test_node("client", NodeType.CLIENT),
            _compute("producer_a"),
            _compute("producer_b"),
            _cache("message_cache"),
            _db("shared_db"),
            edges=[
                _edge("client", "producer_a", SYNCHRONOUS_REST_HTTP),
                _edge("client", "producer_b", SYNCHRONOUS_REST_HTTP),
                _edge("producer_a", "message_cache", SYNCHRONOUS_GRPC),
                _edge("producer_b", "message_cache", SYNCHRONOUS_GRPC),
                _edge("producer_a", "shared_db", SYNCHRONOUS_DATABASE_TCP),
                # producer_b has NO fallback
            ],
        )

        result = CacheUsageValidator().validate(graph)

        miss_errors = [
            e for e in result.errors if isinstance(e, CacheMissPathMissingError)
        ]
        assert len(miss_errors) == 1
        assert miss_errors[0].affected_node_identifiers == [
            "message_cache",
            "producer_b",
        ]


# ------------------------------------------------------ scope boundaries


class TestScopeBoundaries:
    def test_isolated_cache_is_not_double_reported(self) -> None:
        """Fully isolated caches are IsolatedNodeError's job."""
        graph = _graph(
            create_test_node("client", NodeType.CLIENT),
            _compute("processor"),
            _cache("orphan_cache"),
            edges=[
                _edge("client", "processor", SYNCHRONOUS_REST_HTTP),
            ],
        )

        our_result = CacheUsageValidator().validate(graph)
        structural_result = StructuralTopologyValidator().validate(graph)

        assert our_result.is_successful is True
        assert structural_result.is_successful is False

    def test_graph_without_caches_is_accepted(self) -> None:
        graph = _graph(
            create_test_node("client", NodeType.CLIENT),
            _compute("processor"),
            edges=[
                _edge("client", "processor", SYNCHRONOUS_REST_HTTP),
            ],
        )

        result = CacheUsageValidator().validate(graph)

        assert result.is_successful is True

    def test_cyclic_graph_does_not_crash(self) -> None:
        """Set-based rule: cycles are StructuralTopologyValidator's concern."""
        graph = _graph(
            _compute("compute_a"),
            _compute("compute_b"),
            edges=[
                _edge("compute_a", "compute_b", SYNCHRONOUS_GRPC),
                _edge("compute_b", "compute_a", SYNCHRONOUS_GRPC),
            ],
        )

        result = CacheUsageValidator().validate(graph)

        assert result.is_successful is True
        assert result.errors == []
