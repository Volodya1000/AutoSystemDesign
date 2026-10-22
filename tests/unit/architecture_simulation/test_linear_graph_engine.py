"""Check forward C4 path execution with reproducible numeric traces."""

import pytest
from pydantic import ValidationError

from application.architecture_simulation.errors import SimulationEventLimitExceeded
from application.architecture_simulation.graph_execution_errors import (
    GraphExecutionError,
    GraphExecutionFailure,
)
from application.architecture_simulation.graph_mapper import (
    ArchitectureSimulationPlanMapper,
)
from domain.architecture_simulation.graph_execution import (
    GraphRequestTrace,
    GraphTraceWindowResult,
)
from domain.architecture_simulation.graph_plan import GraphSimulationPlan
from domain.architecture_simulation.kernel import SimulationWindow
from domain.models.edges import Edge
from domain.models.nodes import CacheNode, ClientNode, ComputeNode, DatabaseNode
from domain.models.protocols import SYNCHRONOUS_REST_HTTP
from domain.models.scenarios import DesignScenario, WorkloadProfile
from domain.models.topology import ArchitectureGraph
from infrastructure.architecture_simulation.linear_graph_engine import (
    SimPyLinearGraphEngine,
)

pytestmark = pytest.mark.unit


def _compute() -> ComputeNode:
    return ComputeNode(
        identifier="api",
        replicas_count=3,
        maximum_concurrency=10,
        maximum_queue_size=20,
        service_channels_per_replica=2,
        mean_processing_time_milliseconds=50,
        standard_deviation_processing_time=0,
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


def _plan() -> GraphSimulationPlan:
    mapper: ArchitectureSimulationPlanMapper = ArchitectureSimulationPlanMapper()
    graph: ArchitectureGraph = ArchitectureGraph(
        nodes=[ClientNode(identifier="web"), _compute(), _db()],
        edges=[_edge("web", "api"), _edge("api", "db")],
    )
    scenario: DesignScenario = DesignScenario(
        identifier="orders",
        description="Order processing",
        workload=WorkloadProfile(
            baseline_requests_per_second=10,
            peak_requests_per_second=20,
        ),
    )
    return mapper.map(graph, scenario)


def _simulate(
    plan: GraphSimulationPlan,
    arrivals: list[float],
    horizon: float,
    seed: int = 123,
) -> GraphTraceWindowResult:
    engine: SimPyLinearGraphEngine = SimPyLinearGraphEngine()
    return engine.simulate(
        GraphRequestTrace(plan=plan, arrival_times_seconds=arrivals, seed=seed),
        SimulationWindow(
            warmup_seconds=0,
            measurement_seconds=horizon,
            max_events=1000,
        ),
    )


def test_two_node_chain_adds_network_and_service_times() -> None:
    result: GraphTraceWindowResult = _simulate(_plan(), [0], horizon=1)

    assert result.measured_arrivals == 1
    assert result.unfinished == 0
    assert len(result.observations) == 1
    assert result.observations[0].visited_resources == ["api", "db"]
    assert result.observations[0].traversal_seconds == pytest.approx(0.078)
    assert result.queue_model == "unbounded_prototype"


def test_two_simultaneous_requests_queue_at_the_single_channel_database() -> None:
    result: GraphTraceWindowResult = _simulate(_plan(), [0, 0], horizon=0.09)

    assert result.measured_arrivals == 2
    assert result.unfinished == 1
    assert len(result.observations) == 1
    assert result.observations[0].traversal_seconds == pytest.approx(0.078)


def test_results_reproduce_under_identical_seed_and_input() -> None:
    plan: GraphSimulationPlan = _plan()
    plan.resources[0].std_service_seconds = 0.01
    first: GraphTraceWindowResult = _simulate(plan, [0, 0.1, 0.2], 2, seed=55)
    second: GraphTraceWindowResult = _simulate(plan, [0, 0.1, 0.2], 2, seed=55)
    different: GraphTraceWindowResult = _simulate(plan, [0, 0.1, 0.2], 2, seed=56)

    assert first == second
    assert first != different


def test_graph_trace_is_independent_of_resource_input_order() -> None:
    plan: GraphSimulationPlan = _plan()
    reversed_plan: GraphSimulationPlan = plan.model_copy(deep=True)
    reversed_plan.resources.reverse()
    reversed_plan.connections.reverse()

    assert _simulate(plan, [0, 0.1], 2) == _simulate(
        reversed_plan, [0, 0.1], 2
    )


def test_branching_graph_is_rejected_until_routing_semantics_exist() -> None:
    plan: GraphSimulationPlan = _plan()
    plan.connections.append(
        plan.connections[1].model_copy(
            update={"target_identifier": "api"}
        )
    )
    engine: SimPyLinearGraphEngine = SimPyLinearGraphEngine()

    with pytest.raises(GraphExecutionError) as error:
        engine.simulate(
            GraphRequestTrace(plan=plan, arrival_times_seconds=[0], seed=5),
            SimulationWindow(
                warmup_seconds=0, measurement_seconds=10, max_events=100
            ),
        )
    assert error.value.code == GraphExecutionFailure.BRANCHING_UNSUPPORTED


def test_cache_is_not_treated_as_simple_linear_service() -> None:
    plan: GraphSimulationPlan = _plan()
    plan.resources[1].node_type = CacheNode.model_fields["node_type"].default
    engine: SimPyLinearGraphEngine = SimPyLinearGraphEngine()

    with pytest.raises(GraphExecutionError) as error:
        engine.simulate(
            GraphRequestTrace(plan=plan, arrival_times_seconds=[0], seed=5),
            SimulationWindow(
                warmup_seconds=0, measurement_seconds=10, max_events=100
            ),
        )
    assert error.value.code == GraphExecutionFailure.CACHE_UNSUPPORTED


def test_event_budget_interrupts_work_instead_of_returning_partial_success() -> None:
    engine: SimPyLinearGraphEngine = SimPyLinearGraphEngine()
    with pytest.raises(SimulationEventLimitExceeded):
        engine.simulate(
            GraphRequestTrace(
                plan=_plan(), arrival_times_seconds=[0], seed=1
            ),
            SimulationWindow(
                warmup_seconds=0, measurement_seconds=1, max_events=1
            ),
        )


def test_negative_arrival_is_invalid_input() -> None:
    with pytest.raises(ValidationError):
        GraphRequestTrace(plan=_plan(), arrival_times_seconds=[-1], seed=1)


def test_graph_execution_json_round_trip() -> None:
    result: GraphTraceWindowResult = _simulate(_plan(), [0], horizon=1)

    assert result == GraphTraceWindowResult.model_validate_json(
        result.model_dump_json()
    )
