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
    GraphRejectionReason,
    GraphRequestTrace,
    GraphTraceWindowResult,
)
from domain.architecture_simulation.graph_plan import GraphSimulationPlan
from domain.architecture_simulation.kernel import SimulationWindow
from domain.models.enums import NodeType
from infrastructure.architecture_simulation.linear_graph_engine import (
    SimPyLinearGraphEngine,
)
from tests.unit.architecture_simulation.factories import make_graph, make_scenario

pytestmark = pytest.mark.unit


def _plan() -> GraphSimulationPlan:
    mapper: ArchitectureSimulationPlanMapper = ArchitectureSimulationPlanMapper()
    return mapper.map(make_graph(std_milliseconds=0), make_scenario())


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
    assert result.queue_model == "bounded_per_replica"


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

    assert _simulate(plan, [0, 0.1], 2) == _simulate(reversed_plan, [0, 0.1], 2)


def test_invalid_cyclic_routing_plan_is_rejected() -> None:
    plan: GraphSimulationPlan = _plan()
    plan.connections.append(
        plan.connections[1].model_copy(update={"target_identifier": "api"})
    )
    engine: SimPyLinearGraphEngine = SimPyLinearGraphEngine()

    with pytest.raises(GraphExecutionError) as error:
        engine.simulate(
            GraphRequestTrace(plan=plan, arrival_times_seconds=[0], seed=5),
            SimulationWindow(warmup_seconds=0, measurement_seconds=10, max_events=100),
        )
    assert error.value.code == GraphExecutionFailure.BRANCHING_UNSUPPORTED


def test_cache_requires_an_explicit_database_fallback() -> None:
    plan: GraphSimulationPlan = _plan()
    plan.resources[1].node_type = NodeType.CACHE
    engine: SimPyLinearGraphEngine = SimPyLinearGraphEngine()

    with pytest.raises(GraphExecutionError) as error:
        engine.simulate(
            GraphRequestTrace(plan=plan, arrival_times_seconds=[0], seed=5),
            SimulationWindow(warmup_seconds=0, measurement_seconds=10, max_events=100),
        )
    assert error.value.code == GraphExecutionFailure.INVALID_CACHE_TOPOLOGY


def test_event_budget_interrupts_work_instead_of_returning_partial_success() -> None:
    engine: SimPyLinearGraphEngine = SimPyLinearGraphEngine()
    with pytest.raises(SimulationEventLimitExceeded):
        engine.simulate(
            GraphRequestTrace(plan=_plan(), arrival_times_seconds=[0], seed=1),
            SimulationWindow(warmup_seconds=0, measurement_seconds=1, max_events=1),
        )


def test_negative_arrival_is_invalid_input() -> None:
    with pytest.raises(ValidationError):
        GraphRequestTrace(plan=_plan(), arrival_times_seconds=[-1], seed=1)


def test_graph_execution_json_round_trip() -> None:
    result: GraphTraceWindowResult = _simulate(_plan(), [0], horizon=1)

    assert result == GraphTraceWindowResult.model_validate_json(
        result.model_dump_json()
    )


def test_full_database_queue_rejects_without_waiting_indefinitely() -> None:
    plan: GraphSimulationPlan = _plan()
    plan.resources[1].maximum_queue_size_per_replica = 0
    result: GraphTraceWindowResult = _simulate(plan, [0, 0], horizon=1)

    assert result.measured_arrivals == 2
    assert len(result.observations) == 1
    assert len(result.rejections) == 1
    assert result.unfinished == 0
    assert result.rejections[0].node_identifier == "db"
    assert result.rejections[0].replica_index == 0
    assert result.rejections[0].reason_code == GraphRejectionReason.QUEUE_FULL
    assert result.rejections[0].at_seconds == pytest.approx(0.058)


def test_one_waiting_slot_admits_second_request_but_rejects_third() -> None:
    plan: GraphSimulationPlan = _plan()
    plan.resources[1].maximum_queue_size_per_replica = 1
    result: GraphTraceWindowResult = _simulate(plan, [0, 0, 0], horizon=1)

    assert result.measured_arrivals == 3
    assert len(result.observations) == 2
    assert len(result.rejections) == 1
    assert result.unfinished == 0
    assert [observation.traversal_seconds for observation in result.observations] == (
        pytest.approx([0.078, 0.098])
    )
    assert result.rejections[0].reason_code == GraphRejectionReason.QUEUE_FULL


def test_concurrency_limit_can_reject_before_queue_is_full() -> None:
    plan: GraphSimulationPlan = _plan()
    plan.resources[1].maximum_concurrency_per_replica = 1
    plan.resources[1].maximum_queue_size_per_replica = 10
    result: GraphTraceWindowResult = _simulate(plan, [0, 0], horizon=1)

    assert len(result.observations) == 1
    assert len(result.rejections) == 1
    assert result.rejections[0].reason_code == GraphRejectionReason.CONCURRENCY_LIMIT
    assert result.unfinished == 0


def test_rejected_measured_request_does_not_count_as_warmup_outcome() -> None:
    plan: GraphSimulationPlan = _plan()
    plan.resources[1].maximum_queue_size_per_replica = 0
    engine: SimPyLinearGraphEngine = SimPyLinearGraphEngine()
    result: GraphTraceWindowResult = engine.simulate(
        GraphRequestTrace(plan=plan, arrival_times_seconds=[0, 0.001], seed=1),
        SimulationWindow(warmup_seconds=0.001, measurement_seconds=1, max_events=100),
    )

    assert result.warmup_arrivals == 1
    assert result.measured_arrivals == 1
    assert len(result.observations) == 0
    assert len(result.rejections) == 1
    assert result.rejections[0].request_index == 1
    assert result.unfinished == 0


def test_bounded_admission_is_reproducible_for_same_schedule() -> None:
    plan: GraphSimulationPlan = _plan()
    plan.resources[1].maximum_queue_size_per_replica = 0

    assert _simulate(plan, [0, 0, 0], 1) == _simulate(plan, [0, 0, 0], 1)
