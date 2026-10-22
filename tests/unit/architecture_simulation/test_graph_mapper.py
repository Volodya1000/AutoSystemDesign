"""Assert C4 mapping invariants through its public typed domain contract."""

import pytest
from pydantic import ValidationError

from application.architecture_simulation.graph_mapper import (
    ArchitectureSimulationPlanMapper,
    GraphMappingError,
    MappingFailure,
)
from domain.architecture_simulation.graph_plan import GraphSimulationPlan
from domain.models.edges import Edge
from domain.models.enums import EdgeRoutingMode
from domain.models.nodes import (
    CacheNode,
    ClientNode,
    ComputeNode,
    DatabaseNode,
    MessageBrokerNode,
)
from domain.models.protocols import (
    ASYNCHRONOUS_MESSAGE_QUEUE,
    SYNCHRONOUS_REST_HTTP,
)
from domain.models.scenarios import DesignScenario, WorkloadProfile
from domain.models.topology import ArchitectureGraph

pytestmark = pytest.mark.unit


def _compute(identifier: str = "api", channels: int | None = 2) -> ComputeNode:
    return ComputeNode(
        identifier=identifier,
        replicas_count=3,
        maximum_concurrency=10,
        maximum_queue_size=20,
        service_channels_per_replica=channels,
        mean_processing_time_milliseconds=50,
        standard_deviation_processing_time=5,
        monthly_cost_usd=100,
    )


def _db() -> DatabaseNode:
    return DatabaseNode(
        identifier="db",
        maximum_concurrency=5,
        maximum_queue_size=10,
        service_channels_per_replica=1,
        mean_processing_time_milliseconds=20,
        standard_deviation_processing_time=0,
        monthly_cost_usd=70,
    )


def _edge(source: str, target: str) -> Edge:
    return Edge(
        source_identifier=source,
        target_identifier=target,
        protocol=SYNCHRONOUS_REST_HTTP,
        network_latency_milliseconds=4,
    )


def _scenario() -> DesignScenario:
    return DesignScenario(
        identifier="orders",
        description="Order processing",
        workload=WorkloadProfile(
            baseline_requests_per_second=10,
            peak_requests_per_second=20,
        ),
    )


def _graph() -> ArchitectureGraph:
    return ArchitectureGraph(
        nodes=[ClientNode(identifier="web"), _compute(), _db()],
        edges=[_edge("web", "api"), _edge("api", "db")],
    )


def _map(graph: ArchitectureGraph) -> GraphSimulationPlan:
    mapper: ArchitectureSimulationPlanMapper = ArchitectureSimulationPlanMapper()
    return mapper.map(graph, _scenario())


def test_linear_graph_preserves_independent_channels_and_latency_units() -> None:
    plan: GraphSimulationPlan = _map(_graph())

    assert plan.client_identifier == "web"
    assert plan.topological_order == ["web", "api", "db"]
    assert plan.baseline_requests_per_second == 10
    assert plan.peak_requests_per_second == 20
    assert [resource.identifier for resource in plan.resources] == ["api", "db"]
    assert plan.resources[0].replicas_count == 3
    assert plan.resources[0].service_channels_per_replica == 2
    assert plan.resources[0].maximum_concurrency_per_replica == 10
    assert plan.resources[0].maximum_queue_size_per_replica == 20
    assert plan.resources[0].mean_service_seconds == 0.05
    assert plan.resources[0].std_service_seconds == 0.005
    assert plan.connections[0].network_latency_seconds == 0.004
    assert plan.connections[0].timeout_seconds == 5


def test_permuting_nodes_and_edges_does_not_change_the_plan() -> None:
    original: ArchitectureGraph = _graph()
    reordered: ArchitectureGraph = ArchitectureGraph(
        nodes=list(reversed(original.nodes)),
        edges=list(reversed(original.edges)),
    )
    assert _map(original) == _map(reordered)


def test_branch_preserves_explicit_routing_modes_without_simulating_them() -> None:
    cache: CacheNode = CacheNode(
        identifier="cache",
        service_channels_per_replica=1,
        maximum_concurrency=2,
        maximum_queue_size=3,
        mean_processing_time_milliseconds=3,
        standard_deviation_processing_time=0,
        monthly_cost_usd=20,
        cache_hit_rate_probability=0.7,
    )
    graph: ArchitectureGraph = _graph()
    graph.nodes.append(cache)
    graph.edges.append(
        Edge(
            source_identifier="api",
            target_identifier="cache",
            protocol=SYNCHRONOUS_REST_HTTP,
            routing_mode=EdgeRoutingMode.FAN_OUT,
        )
    )
    plan: GraphSimulationPlan = _map(graph)

    assert plan.resources[1].cache_hit_probability == 0.7
    assert plan.connections[1].routing_mode == EdgeRoutingMode.FAN_OUT


def test_missing_service_channels_are_not_guessed_from_concurrency() -> None:
    graph: ArchitectureGraph = ArchitectureGraph(
        nodes=[ClientNode(identifier="web"), _compute(channels=None)],
        edges=[_edge("web", "api")],
    )
    with pytest.raises(GraphMappingError) as error:
        _map(graph)
    assert error.value.code == MappingFailure.SERVICE_CHANNELS_UNKNOWN


def test_missing_workload_does_not_invent_an_arrival_rate() -> None:
    mapper: ArchitectureSimulationPlanMapper = ArchitectureSimulationPlanMapper()
    scenario: DesignScenario = DesignScenario(
        identifier="orders", description="Order processing"
    )
    with pytest.raises(GraphMappingError) as error:
        mapper.map(_graph(), scenario)
    assert error.value.code == MappingFailure.MISSING_WORKLOAD


@pytest.mark.parametrize(
    ("edges", "reason"),
    [
        ([_edge("web", "missing")], MappingFailure.UNKNOWN_ENDPOINT),
        ([_edge("web", "api"), _edge("web", "api")], MappingFailure.DUPLICATE_EDGE),
        (
            [_edge("web", "api"), _edge("api", "db"), _edge("db", "api")],
            MappingFailure.CYCLE,
        ),
    ],
)
def test_inconsistent_topology_has_a_typed_failure(
    edges: list[Edge], reason: MappingFailure
) -> None:
    graph: ArchitectureGraph = _graph()
    graph.edges = edges
    with pytest.raises(GraphMappingError) as error:
        _map(graph)
    assert error.value.code == reason


def test_isolated_capacity_node_is_rejected() -> None:
    graph: ArchitectureGraph = _graph()
    graph.edges = [_edge("web", "api")]
    with pytest.raises(GraphMappingError) as error:
        _map(graph)
    assert error.value.code == MappingFailure.DISCONNECTED


def test_duplicate_identifier_is_rejected() -> None:
    graph: ArchitectureGraph = _graph()
    graph.nodes.append(_compute())
    with pytest.raises(GraphMappingError) as error:
        _map(graph)
    assert error.value.code == MappingFailure.DUPLICATE_NODE


def test_asynchronous_edges_are_not_silently_treated_as_sync() -> None:
    graph: ArchitectureGraph = _graph()
    graph.edges[0].protocol = ASYNCHRONOUS_MESSAGE_QUEUE
    with pytest.raises(GraphMappingError) as error:
        _map(graph)
    assert error.value.code == MappingFailure.UNSUPPORTED_ASYNC


def test_retries_cannot_be_silently_ignored() -> None:
    graph: ArchitectureGraph = _graph()
    graph.edges[0].retry_attempts_count = 1
    with pytest.raises(GraphMappingError) as error:
        _map(graph)
    assert error.value.code == MappingFailure.UNSUPPORTED_RETRY


def test_broker_requires_an_explicit_execution_semantics() -> None:
    broker: MessageBrokerNode = MessageBrokerNode(
        identifier="mq",
        service_channels_per_replica=1,
        maximum_concurrency=2,
        mean_processing_time_milliseconds=1,
        standard_deviation_processing_time=0,
        monthly_cost_usd=5,
    )
    graph: ArchitectureGraph = ArchitectureGraph(
        nodes=[ClientNode(identifier="web"), broker],
        edges=[_edge("web", "mq")],
    )
    with pytest.raises(GraphMappingError) as error:
        _map(graph)
    assert error.value.code == MappingFailure.UNSUPPORTED_BROKER


def test_plan_json_round_trip() -> None:
    plan: GraphSimulationPlan = _map(_graph())
    assert GraphSimulationPlan.model_validate_json(plan.model_dump_json()) == plan


def test_non_finite_resource_times_are_rejected_by_contract() -> None:
    plan: GraphSimulationPlan = _map(_graph())
    with pytest.raises(ValidationError):
        plan.resources[0].model_copy(
            update={"mean_service_seconds": float("inf")}
        ).model_validate(plan.resources[0].model_dump())
