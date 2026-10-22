"""Cross-layer tests for the canonical compute-owned cache miss path."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from application.architecture_simulation.graph_mapper import (
    ArchitectureSimulationPlanMapper,
)
from domain.architecture_simulation.graph_execution import (
    GraphRequestTrace,
    GraphTraceWindowResult,
)
from domain.architecture_simulation.kernel import SimulationWindow
from domain.models.nodes import ClientNode
from domain.models.topology import ArchitectureGraph
from domain.specifications.cache_usage_validator import CacheUsageValidator
from domain.specifications.structural_validator import StructuralTopologyValidator
from domain.specifications.traffic_flow import compute_node_incoming_rps
from infrastructure.architecture_simulation.linear_graph_engine import (
    SimPyLinearGraphEngine,
)
from tests.unit.architecture_simulation.factories import (
    make_cache,
    make_cache_graph,
    make_compute,
    make_database,
    make_edge,
    make_scenario,
)

if TYPE_CHECKING:
    from domain.architecture_simulation.graph_plan import GraphSimulationPlan

pytestmark = pytest.mark.unit


def _simulate(
    graph: ArchitectureGraph, arrivals: list[float]
) -> GraphTraceWindowResult:
    """Run the actual mapper and SimPy engine over a C4 graph."""
    plan: GraphSimulationPlan = ArchitectureSimulationPlanMapper().map(
        graph, make_scenario()
    )
    return SimPyLinearGraphEngine().simulate(
        GraphRequestTrace(plan=plan, arrival_times_seconds=arrivals, seed=67),
        SimulationWindow(
            warmup_seconds=0,
            measurement_seconds=220,
            max_events=50_000,
        ),
    )


def _incoming_rps(graph: ArchitectureGraph) -> dict[str, float]:
    """Propagate the same canonical C4 graph with the scenario's load."""
    scenario = make_scenario()
    assert scenario.workload is not None
    return compute_node_incoming_rps(graph, scenario.workload)


@pytest.mark.parametrize(
    ("hit_probability", "expected_db_fraction"),
    [
        (0.0, 1.0),
        (0.4, 0.6),
        (1.0, 0.0),
    ],
)
def test_c4_analytics_and_simpy_agree_on_cache_misses(
    hit_probability: float, expected_db_fraction: float
) -> None:
    """Each lookup reaches cache; only misses reach its sibling DB edge."""
    graph: ArchitectureGraph = make_cache_graph(hit_probability)
    assert StructuralTopologyValidator().validate(graph).is_successful
    assert CacheUsageValidator().validate(graph).is_successful

    incoming_rps: dict[str, float] = _incoming_rps(graph)
    assert incoming_rps["cache"] == pytest.approx(20)
    assert incoming_rps["db"] == pytest.approx(20 * expected_db_fraction)

    arrivals: list[float] = [index * 0.2 for index in range(1000)]
    result: GraphTraceWindowResult = _simulate(graph, arrivals)
    db_visits: int = sum(
        "db" in observation.visited_resources for observation in result.observations
    )
    assert result.measured_arrivals == len(arrivals)
    assert len(result.observations) == len(arrivals)
    assert result.rejections == []
    assert result.unfinished == 0
    assert all(
        observation.visited_resources[:2] == ["api", "cache"]
        for observation in result.observations
    )
    if expected_db_fraction in (0.0, 1.0):
        assert db_visits == len(arrivals) * expected_db_fraction
    else:
        assert db_visits == pytest.approx(
            len(arrivals) * expected_db_fraction, abs=80
        )


def test_multiple_cache_readers_keep_separate_fallbacks_and_root_identity() -> None:
    """A shared cache never makes one reader issue another reader's DB call."""
    graph: ArchitectureGraph = ArchitectureGraph(
        nodes=[
            ClientNode(identifier="web"),
            make_compute("api_a", std_milliseconds=0),
            make_compute("api_b", std_milliseconds=0),
            make_cache(0.5),
            make_database().model_copy(update={"identifier": "db_a"}),
            make_database().model_copy(update={"identifier": "db_b"}),
        ],
        edges=[
            make_edge("web", "api_a"),
            make_edge("web", "api_b"),
            make_edge("api_a", "cache"),
            make_edge("api_b", "cache"),
            make_edge("api_a", "db_a"),
            make_edge("api_b", "db_b"),
        ],
    )
    assert StructuralTopologyValidator().validate(graph).is_successful
    assert CacheUsageValidator().validate(graph).is_successful

    rps: dict[str, float] = _incoming_rps(graph)
    assert rps["cache"] == pytest.approx(20)
    assert rps["db_a"] == pytest.approx(5)
    assert rps["db_b"] == pytest.approx(5)

    arrivals: list[float] = [index * 0.2 for index in range(500)]
    result: GraphTraceWindowResult = _simulate(graph, arrivals)
    assert result.measured_arrivals == 500
    assert len(result.observations) == 500
    assert result.rejections == []
    assert result.unfinished == 0
    reader_databases: dict[str, str] = {"api_a": "db_a", "api_b": "db_b"}
    for observation in result.observations:
        visited: list[str] = observation.visited_resources
        assert visited[0] in reader_databases
        assert visited[1] == "cache"
        if len(visited) == 3:
            assert visited[2] == reader_databases[visited[0]]
        else:
            assert len(visited) == 2

    reversed_graph: ArchitectureGraph = graph.model_copy(deep=True)
    reversed_graph.edges.reverse()
    assert _simulate(reversed_graph, arrivals) == result


def test_legacy_cache_to_database_edge_is_not_a_valid_c4_contract() -> None:
    """Reject the misleading physical edge instead of changing C4 rules."""
    graph: ArchitectureGraph = make_cache_graph(0.5)
    graph.edges[-1].source_identifier = "cache"

    assert not StructuralTopologyValidator().validate(graph).is_successful
    assert not CacheUsageValidator().validate(graph).is_successful
