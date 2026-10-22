"""Exercise alternative and cache policies via public graph simulation contracts."""

import pytest

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
from domain.models.enums import EdgeRoutingMode
from domain.models.nodes import ClientNode
from domain.models.topology import ArchitectureGraph
from infrastructure.architecture_simulation.linear_graph_engine import (
    SimPyLinearGraphEngine,
)
from infrastructure.architecture_simulation.routing import StochasticRouteSelector
from tests.unit.architecture_simulation.factories import (
    make_cache,
    make_compute,
    make_database,
    make_edge,
    make_scenario,
)

pytestmark = pytest.mark.unit


def _alternative_plan() -> GraphSimulationPlan:
    graph: ArchitectureGraph = ArchitectureGraph(
        nodes=[
            ClientNode(identifier="web"),
            make_compute(std_milliseconds=0),
            make_database().model_copy(update={"identifier": "db_a"}),
            make_database().model_copy(update={"identifier": "db_b"}),
        ],
        edges=[
            make_edge("web", "api"),
            make_edge("api", "db_a"),
            make_edge("api", "db_b"),
        ],
    )
    return ArchitectureSimulationPlanMapper().map(graph, make_scenario())


def _cache_plan(hit_probability: float) -> GraphSimulationPlan:
    graph: ArchitectureGraph = ArchitectureGraph(
        nodes=[
            ClientNode(identifier="web"),
            make_compute(std_milliseconds=0),
            make_cache(hit_probability),
            make_database(),
        ],
        edges=[
            make_edge("web", "api"),
            make_edge("api", "cache"),
            make_edge("api", "db"),
        ],
    )
    return ArchitectureSimulationPlanMapper().map(graph, make_scenario())


def _simulate(plan: GraphSimulationPlan) -> GraphTraceWindowResult:
    return SimPyLinearGraphEngine().simulate(
        GraphRequestTrace(plan=plan, arrival_times_seconds=[0], seed=99),
        SimulationWindow(
            warmup_seconds=0, measurement_seconds=1, max_events=200
        ),
    )


def test_alternative_routes_select_exactly_one_database_per_request() -> None:
    plan: GraphSimulationPlan = _alternative_plan()
    result: GraphTraceWindowResult = SimPyLinearGraphEngine().simulate(
        GraphRequestTrace(
            plan=plan,
            arrival_times_seconds=[0.1 * index for index in range(10)],
            seed=2,
        ),
        SimulationWindow(
            warmup_seconds=0, measurement_seconds=3, max_events=1000
        ),
    )

    assert result.measured_arrivals == 10
    assert len(result.observations) == 10
    assert len(result.rejections) == 0
    assert result.unfinished == 0
    assert all(
        len(item.visited_resources) == 2
        and item.visited_resources[0] == "api"
        and item.visited_resources[1] in {"db_a", "db_b"}
        for item in result.observations
    )


def test_seeded_routing_does_not_depend_on_connections_order() -> None:
    plan: GraphSimulationPlan = _alternative_plan()
    shuffled: GraphSimulationPlan = plan.model_copy(deep=True)
    shuffled.connections.reverse()
    selector: StochasticRouteSelector = StochasticRouteSelector()
    selector.validate(plan)
    selector.validate(shuffled)

    assert all(
        selector.select(plan, seed=41, request_index=index)
        == selector.select(shuffled, seed=41, request_index=index)
        for index in range(100)
    )


def test_both_alternatives_receive_events_over_many_root_requests() -> None:
    plan: GraphSimulationPlan = _alternative_plan()
    selector: StochasticRouteSelector = StochasticRouteSelector()
    selected: set[str] = {
        selector.select(plan, seed=3, request_index=index)[-1][1].identifier
        for index in range(100)
    }
    assert selected == {"db_a", "db_b"}


@pytest.mark.parametrize(
    ("probability", "expected_path", "expected_duration"),
    [
        (1.0, ["api", "cache"], 0.061),
        (0.0, ["api", "cache", "db"], 0.085),
    ],
)
def test_cache_hit_skips_db_and_miss_calls_it_once(
    probability: float, expected_path: list[str], expected_duration: float
) -> None:
    result: GraphTraceWindowResult = _simulate(_cache_plan(probability))
    assert result.measured_arrivals == 1
    assert len(result.rejections) == 0
    assert len(result.observations) == 1
    assert result.observations[0].visited_resources == expected_path
    assert result.observations[0].traversal_seconds == pytest.approx(
        expected_duration
    )


def test_cache_hits_are_seeded_for_each_request_not_whole_experiment() -> None:
    plan: GraphSimulationPlan = _cache_plan(0.5)
    selector: StochasticRouteSelector = StochasticRouteSelector()
    selector.validate(plan)
    routes: list[list[str]] = [
        [
            resource.identifier
            for _, resource in selector.select(plan, seed=2, request_index=index)
        ]
        for index in range(100)
    ]

    assert any(route == ["api", "cache"] for route in routes)
    assert any(route == ["api", "cache", "db"] for route in routes)


def test_fan_out_is_rejected_without_explicit_join_semantics() -> None:
    plan: GraphSimulationPlan = _alternative_plan()
    plan.connections[1].routing_mode = EdgeRoutingMode.FAN_OUT
    selector: StochasticRouteSelector = StochasticRouteSelector()

    with pytest.raises(GraphExecutionError) as error:
        selector.validate(plan)
    assert error.value.code == GraphExecutionFailure.BRANCHING_UNSUPPORTED


def test_cache_cannot_invent_a_missing_fallback() -> None:
    plan: GraphSimulationPlan = _cache_plan(hit_probability=1)
    plan.connections = [
        connection
        for connection in plan.connections
        if connection.target_identifier != "db"
    ]
    selector: StochasticRouteSelector = StochasticRouteSelector()

    with pytest.raises(GraphExecutionError) as error:
        selector.validate(plan)
    assert error.value.code == GraphExecutionFailure.INVALID_CACHE_TOPOLOGY
