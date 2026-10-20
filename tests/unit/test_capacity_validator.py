"""Unit tests of CapacitySaturationValidator and compute_node_utilization.

Numeric cases are computed by hand and documented in each test so the
saturation threshold (98%), the max_rps formula
(replicas x concurrency x 1000 / mean_ms) and the fan-out flow split stay
honest. No LLM, no I/O: pure domain logic.
"""

from __future__ import annotations

import pytest

from domain.exceptions.architecture_errors import CapacitySaturationError
from domain.models.enums import NodeType
from domain.models.scenarios import DesignScenario, WorkloadProfile
from domain.models.topology import AnyNode, ArchitectureGraph
from domain.specifications.capacity_validator import (
    SATURATION_THRESHOLD,
    CapacitySaturationValidator,
    compute_node_utilization,
)
from tests.factories import (
    create_test_compute_node,
    create_test_edge,
    create_test_node,
)

pytestmark = pytest.mark.unit


# ------------------------------------------------------------------ helpers


def _scenario(peak_rps: float) -> DesignScenario:
    return DesignScenario(
        identifier="capacity_test",
        description="Capacity saturation scenario",
        workload=WorkloadProfile(
            baseline_requests_per_second=max(1.0, peak_rps / 2.0),
            peak_requests_per_second=peak_rps,
        ),
    )


def _chain_graph(*nodes: AnyNode) -> ArchitectureGraph:
    """Linear client → n1 → n2 → ... chain; first node must be a ClientNode."""
    edges = [
        create_test_edge(nodes[index].identifier, nodes[index + 1].identifier)
        for index in range(len(nodes) - 1)
    ]
    return ArchitectureGraph(nodes=list(nodes), edges=edges)


# ---------------------------------------------------------------- threshold


class TestSaturationThresholdConstant:
    def test_threshold_is_98_percent(self) -> None:
        """Roadmap F4 pins the threshold at 98%: no config, no tuning."""
        assert SATURATION_THRESHOLD == EXPECTED_ASSERT_SATURATION_THRESHOLD


# -------------------------------------------------------- below threshold


class TestBelowThreshold:
    def test_low_utilization_yields_no_errors(self) -> None:
        """Manual: max_rps = 1 x 100 x 1000 / 10 = 10_000.

        peak = 1_000 → util = 0.10 = 10%. Well under 98% → no error.
        """
        graph = _chain_graph(
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node("compute_1"),
        )
        result = CapacitySaturationValidator().validate(graph, _scenario(1_000.0))
        assert result.is_successful is True
        assert result.errors == []

    def test_utilization_is_reported_even_below_threshold(self) -> None:
        """compute_node_utilization always reports every capacity node."""
        graph = _chain_graph(
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node("compute_1"),
        )
        utilization = compute_node_utilization(graph, _scenario(1_000.0))
        assert utilization == {"compute_1": pytest.approx(0.10, rel=1e-9)}


# --------------------------------------------------------- boundary values


class TestBoundaryAt98Percent:
    def test_just_below_threshold_passes(self) -> None:
        """Manual: max_rps = 10_000. peak = 9_799 → util = 0.9799 → OK.

        This is the last integer peak that is strictly below the 98% bar.
        """
        graph = _chain_graph(
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node("compute_1"),
        )
        result = CapacitySaturationValidator().validate(graph, _scenario(9_799.0))
        assert result.is_successful is True

    def test_exactly_at_threshold_fails(self) -> None:
        """Manual: max_rps = 10_000. peak = 9_800 → util = 0.98 exactly.

        The comparison is `>=`, so equality already counts as saturation:
        an unbounded queue forms at 100% offered load, and 0.98 is the
        roadmap's safety margin below that.
        """
        graph = _chain_graph(
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node("compute_1"),
        )
        result = CapacitySaturationValidator().validate(graph, _scenario(9_800.0))
        assert result.is_successful is False
        assert result.has_error(CapacitySaturationError)

        error = result.errors[0]
        assert isinstance(error, CapacitySaturationError)
        assert error.affected_node_identifiers == ["compute_1"]
        assert "compute_1" in error.message
        # utilization_percentage = 0.98 * 100 = 98.0 → "98.0%"
        assert "98.0%" in error.message
        assert "9800.0 RPS" in error.message
        assert "10000.0 RPS" in error.message


# -------------------------------------------------------- above threshold


class TestAboveThreshold:
    def test_overload_reports_arrival_and_maximum(self) -> None:
        """Manual: max_rps = 10_000. peak = 10_500 → util = 1.05 = 105%.

        arrival_rate_rps ≈ 10_500, maximum_capacity_rps ≈ 10_000.
        """
        graph = _chain_graph(
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node("compute_1"),
        )
        result = CapacitySaturationValidator().validate(graph, _scenario(10_500.0))

        assert result.is_successful is False
        errors = [e for e in result.errors if isinstance(e, CapacitySaturationError)]
        assert len(errors) == 1
        assert errors[0].affected_node_identifiers == ["compute_1"]
        # The message format is owned by the error class; do not pin its
        # exact layout, only the numeric facts it must carry.
        assert "compute_1" in errors[0].message
        assert "105.0%" in errors[0].message
        assert "10500.0 RPS" in errors[0].message
        assert "10000.0 RPS" in errors[0].message


# ------------------------------------------------------ multiple replicas


class TestReplicasMultiplyCapacity:
    def test_two_replicas_double_max_rps(self) -> None:
        """Manual: replicas = 2 → max_rps = 2 x 100 x 1000 / 10 = 20_000.

        peak = 15_000 → util = 0.75 → no error.

        A single replica would have produced util = 1.5 (an error). This
        test pins that replicas_count participates in the formula, not just
        maximum_concurrency.
        """
        graph = _chain_graph(
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node("compute_1", replicas=2),
        )
        result = CapacitySaturationValidator().validate(graph, _scenario(15_000.0))
        assert result.is_successful is True

        utilization = compute_node_utilization(graph, _scenario(15_000.0))
        assert utilization["compute_1"] == pytest.approx(0.75, rel=1e-9)


# ----------------------------------------------- multiple nodes, mixed load


class TestMultipleNodes:
    def test_only_overloaded_node_is_reported(self) -> None:
        """Manual: peak = 120_000 split equally across two clients → 60_000 each.

        compute_1: c = 1_200, mean = 10 ms → max = 120_000,
        util = 60_000 / 120_000 = 0.5
        compute_2: c = 500, mean = 10 ms → max = 50_000,
        util = 60_000 / 50_000 = 1.2

        Only compute_2 crosses 98%; compute_1's error list must stay empty.
        """
        client_1 = create_test_node("client_1", NodeType.CLIENT)
        client_2 = create_test_node("client_2", NodeType.CLIENT)
        compute_1 = create_test_compute_node("compute_1", concurrency=1_200)
        compute_2 = create_test_compute_node("compute_2", concurrency=500)

        graph = ArchitectureGraph(
            nodes=[client_1, client_2, compute_1, compute_2],
            edges=[
                create_test_edge("client_1", "compute_1"),
                create_test_edge("client_2", "compute_2"),
            ],
        )

        result = CapacitySaturationValidator().validate(graph, _scenario(120_000.0))

        assert result.is_successful is False
        saturation_errors = [
            e for e in result.errors if isinstance(e, CapacitySaturationError)
        ]
        assert len(saturation_errors) == 1
        assert saturation_errors[0].affected_node_identifiers == ["compute_2"]

        utilization = compute_node_utilization(graph, _scenario(120_000.0))
        assert utilization["compute_1"] == pytest.approx(0.5, rel=1e-9)
        assert utilization["compute_2"] == pytest.approx(1.2, rel=1e-9)


# ------------------------------------------------------- missing workload


class TestMissingWorkload:
    def test_compute_node_utilization_returns_empty_dict(self) -> None:
        graph = _chain_graph(
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node("compute_1"),
        )
        scenario = DesignScenario(
            identifier="no_workload",
            description="Workload deliberately absent",
            workload=None,
        )
        assert not compute_node_utilization(graph, scenario)

    def test_validator_returns_empty_result(self) -> None:
        graph = _chain_graph(
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node("compute_1"),
        )
        scenario = DesignScenario(
            identifier="no_workload",
            description="Workload deliberately absent",
            workload=None,
        )
        result = CapacitySaturationValidator().validate(graph, scenario)
        assert result.is_successful is True
        assert result.errors == []


# ------------------------------------------------------ client exclusion


class TestClientNodeExclusion:
    def test_client_not_present_in_utilization_dict(self) -> None:
        """Exclude client nodes from capacity utilization.

        ClientNode has no capacity fields and must never be the target of a
        saturation error.
        """
        graph = _chain_graph(
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node("compute_1"),
        )
        utilization = compute_node_utilization(graph, _scenario(1_000.0))
        assert "client" not in utilization
        assert set(utilization) == {"compute_1"}

    def test_client_does_not_trigger_saturation(self) -> None:
        """Never flag a client node, even at a huge flow.

        ClientNode has no capacity or queue and must not produce an error.
        """
        graph = _chain_graph(
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node("compute_1", concurrency=10_000, mean_ms=1.0),
        )
        result = CapacitySaturationValidator().validate(graph, _scenario(1_000_000.0))
        assert result.is_successful is True


# -------------------------------------------------------- cycle tolerance


class TestCycleTolerance:
    def test_cyclic_graph_is_skipped_without_crashing(self) -> None:
        """The workload validator must not raise on a cyclic graph.

        Cycles are reported by StructuralTopologyValidator, which runs in
        the same aggregation pass as CapacitySaturationValidator. If F4
        propagated the ValueError from ``compute_node_incoming_rps``, the
        whole repair loop would abort before the model ever sees the cycle
        error. Instead F4 must yield and return an empty result so the
        structural error reaches the repair prompt.
        """
        compute_1 = create_test_node("compute_1", NodeType.COMPUTE)
        compute_2 = create_test_node("compute_2", NodeType.COMPUTE)
        graph = ArchitectureGraph(
            nodes=[compute_1, compute_2],
            edges=[
                create_test_edge("compute_1", "compute_2"),
                create_test_edge("compute_2", "compute_1"),
            ],
        )
        scenario = DesignScenario(
            identifier="cyclic_graph",
            description="Cyclic topology for cycle-tolerance test",
            workload=WorkloadProfile(
                baseline_requests_per_second=1.0,
                peak_requests_per_second=2.0,
            ),
        )

        result = CapacitySaturationValidator().validate(graph, scenario)

        assert result.is_successful is True
        assert result.errors == []

EXPECTED_ASSERT_SATURATION_THRESHOLD = 0.98
