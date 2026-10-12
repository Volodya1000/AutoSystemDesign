"""Unit tests of the BudgetValidator scenario validator."""

import pytest

from domain.exceptions.architecture_errors import BudgetExceededError
from domain.models.nodes import ClientNode, ComputeNode, DatabaseNode
from domain.models.requirements import BudgetRequirement, LatencyRequirement
from domain.models.scenarios import DesignScenario, WorkloadProfile
from domain.models.topology import AnyNode, ArchitectureGraph
from domain.specifications.budget_validator import BudgetValidator
from domain.specifications.interfaces import ValidationResult

pytestmark = pytest.mark.unit


def _compute_node(identifier: str, cost: float) -> ComputeNode:
    return ComputeNode(
        identifier=identifier,
        maximum_concurrency=100,
        maximum_queue_size=500,
        mean_processing_time_milliseconds=10.0,
        standard_deviation_processing_time=2.0,
        monthly_cost_usd=cost,
    )


def _database_node(identifier: str, cost: float) -> DatabaseNode:
    return DatabaseNode(
        identifier=identifier,
        maximum_concurrency=100,
        maximum_queue_size=500,
        mean_processing_time_milliseconds=10.0,
        standard_deviation_processing_time=2.0,
        monthly_cost_usd=cost,
    )


def _graph(*nodes: AnyNode) -> ArchitectureGraph:
    return ArchitectureGraph(nodes=list(nodes), edges=[])


def _scenario(*requirements) -> DesignScenario:
    return DesignScenario(
        identifier="budget_test",
        description="Budget validation scenario",
        workload=WorkloadProfile(
            baseline_requests_per_second=10.0,
            peak_requests_per_second=20.0,
        ),
        requirements=list(requirements),
    )


class TestBudgetValidator:
    """Numeric cases: normal / boundary / exceeded / multiple requirements."""

    def test_no_errors_when_total_cost_is_below_limit(self) -> None:
        graph: ArchitectureGraph = _graph(
            _compute_node("compute_1", 500.0),
            _compute_node("compute_2", 500.0),
        )
        scenario: DesignScenario = _scenario(BudgetRequirement(threshold_value=2000.0))
        result: ValidationResult = BudgetValidator().validate(graph, scenario)
        assert result.is_successful
        assert result.errors == []

    def test_no_errors_when_total_cost_equals_limit(self) -> None:
        """Boundary: <= operator accepts exact equality."""
        graph: ArchitectureGraph = _graph(
            _compute_node("compute_1", 1000.0),
            _compute_node("compute_2", 1000.0),
        )
        scenario: DesignScenario = _scenario(BudgetRequirement(threshold_value=2000.0))
        result: ValidationResult = BudgetValidator().validate(graph, scenario)
        assert result.is_successful

    def test_budget_exceeded_reports_total_and_limit(self) -> None:
        graph: ArchitectureGraph = _graph(
            _compute_node("compute_1", 1500.0),
            _database_node("database_1", 2000.0),
        )
        scenario: DesignScenario = _scenario(BudgetRequirement(threshold_value=3000.0))
        result: ValidationResult = BudgetValidator().validate(graph, scenario)

        assert result.has_error(BudgetExceededError)
        error: BudgetExceededError = next(
            e for e in result.errors if isinstance(e, BudgetExceededError)
        )
        assert error.error_code == "BUDGET_EXCEEDED"
        assert error.total_monthly_cost_usd == 3500.0
        assert error.budget_limit_usd == 3000.0
        assert "3500.00" in error.message
        assert "3000.00" in error.message

    def test_no_budget_requirement_is_a_no_op(self) -> None:
        graph: ArchitectureGraph = _graph(_compute_node("compute_1", 10_000.0))
        scenario: DesignScenario = _scenario(LatencyRequirement(threshold_value=300.0))
        result: ValidationResult = BudgetValidator().validate(graph, scenario)
        assert result.is_successful

    def test_client_nodes_are_excluded_from_total_cost(self) -> None:
        """ClientNode has no monthly_cost_usd: it must not contribute."""
        graph: ArchitectureGraph = _graph(
            ClientNode(identifier="web_client"),
            _compute_node("compute_1", 3000.0),
        )
        scenario: DesignScenario = _scenario(BudgetRequirement(threshold_value=3000.0))
        result: ValidationResult = BudgetValidator().validate(graph, scenario)
        assert result.is_successful

    def test_each_violated_requirement_produces_its_own_error(self) -> None:
        graph: ArchitectureGraph = _graph(_compute_node("compute_1", 5000.0))
        scenario: DesignScenario = _scenario(
            BudgetRequirement(threshold_value=3000.0),
            BudgetRequirement(threshold_value=4000.0),
        )
        result: ValidationResult = BudgetValidator().validate(graph, scenario)

        budget_errors: list[BudgetExceededError] = [
            e for e in result.errors if isinstance(e, BudgetExceededError)
        ]
        assert len(budget_errors) == 2
        limits: list[float] = sorted(e.budget_limit_usd for e in budget_errors)
        assert limits == [3000.0, 4000.0]
        assert all(e.total_monthly_cost_usd == 5000.0 for e in budget_errors)

    def test_only_violated_requirements_produce_errors(self) -> None:
        graph: ArchitectureGraph = _graph(_compute_node("compute_1", 3500.0))
        scenario: DesignScenario = _scenario(
            BudgetRequirement(threshold_value=3000.0),  # violated
            BudgetRequirement(threshold_value=4000.0),  # satisfied
        )
        result: ValidationResult = BudgetValidator().validate(graph, scenario)

        budget_errors: list[BudgetExceededError] = [
            e for e in result.errors if isinstance(e, BudgetExceededError)
        ]
        assert len(budget_errors) == 1
        assert budget_errors[0].budget_limit_usd == 3000.0
