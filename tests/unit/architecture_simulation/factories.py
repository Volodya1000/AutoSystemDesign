"""Build one canonical, strictly typed C4 scenario for simulation tests."""

from domain.models.edges import Edge
from domain.models.nodes import CacheNode, ClientNode, ComputeNode, DatabaseNode
from domain.models.protocols import SYNCHRONOUS_REST_HTTP
from domain.models.scenarios import DesignScenario, WorkloadProfile
from domain.models.topology import ArchitectureGraph


def make_compute(
    identifier: str = "api",
    channels: int | None = 2,
    std_milliseconds: float = 5.0,
) -> ComputeNode:
    """Build an API resource without collapsing channels into concurrency."""
    return ComputeNode(
        identifier=identifier,
        replicas_count=3,
        maximum_concurrency=10,
        maximum_queue_size=20,
        service_channels_per_replica=channels,
        mean_processing_time_milliseconds=50,
        standard_deviation_processing_time=std_milliseconds,
        monthly_cost_usd=100,
    )


def make_cache(
    hit_probability: float, identifier: str = "cache"
) -> CacheNode:
    """Build one deterministic cache resource for cross-layer tests."""
    return CacheNode(
        identifier=identifier,
        service_channels_per_replica=1,
        maximum_concurrency=3,
        maximum_queue_size=4,
        mean_processing_time_milliseconds=3,
        standard_deviation_processing_time=0,
        monthly_cost_usd=20,
        cache_hit_rate_probability=hit_probability,
    )


def make_database() -> DatabaseNode:
    """Build a fixed-duration single-channel database."""
    return DatabaseNode(
        identifier="db",
        maximum_concurrency=5,
        maximum_queue_size=10,
        service_channels_per_replica=1,
        mean_processing_time_milliseconds=20,
        standard_deviation_processing_time=0,
        monthly_cost_usd=70,
    )


def make_edge(source: str, target: str) -> Edge:
    """Connect two resources with known one-way network latency."""
    return Edge(
        source_identifier=source,
        target_identifier=target,
        protocol=SYNCHRONOUS_REST_HTTP,
        network_latency_milliseconds=4,
    )


def make_graph(std_milliseconds: float = 5.0) -> ArchitectureGraph:
    """Build the connected Client → API → Database topology."""
    return ArchitectureGraph(
        nodes=[
            ClientNode(identifier="web"),
            make_compute(std_milliseconds=std_milliseconds),
            make_database(),
        ],
        edges=[make_edge("web", "api"), make_edge("api", "db")],
    )


def make_scenario() -> DesignScenario:
    """Build baseline and peak RPS without an LLM dependency."""
    return DesignScenario(
        identifier="orders",
        description="Order processing",
        workload=WorkloadProfile(
            baseline_requests_per_second=10,
            peak_requests_per_second=20,
        ),
    )
