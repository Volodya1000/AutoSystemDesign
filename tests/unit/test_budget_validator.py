"""Unit tests of BudgetRequirementValidator and the requirement dispatcher."""

import pytest

from domain.exceptions.architecture_errors import BudgetExceededError
from domain.models.nodes import ClientNode, ComputeNode, DatabaseNode
from domain.models.requirements import (
    BudgetRequirement,
    LatencyRequirement,
    Requirement,
)
from domain.models.scenarios import DesignScenario, WorkloadProfile
from domain.models.topology import AnyNode, ArchitectureGraph
from domain.specifications.budget_validator import BudgetRequirementValidator
from domain.specifications.interfaces import RequirementValidator
from domain.specifications.requirement_dispatch import (
    RequirementValidationDispatcher,
)

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


def _scenario(*requirements: Requirement) -> DesignScenario:
    return DesignScenario(
        identifier="budget_test",
        description="Budget validation scenario",
        workload=WorkloadProfile(
            baseline_requests_per_second=10.0,
            peak_requests_per_second=20.0,
        ),
        requirements=list(requirements),
    )


class TestBudgetRequirementValidator:
    """Numeric cases: normal / boundary / exceeded."""

    def test_no_errors_when_total_cost_is_below_limit(self) -> None:
        graph: ArchitectureGraph = _graph(
            _compute_node("compute_1", 500.0),
            _compute_node("compute_2", 500.0),
        )
        errors = BudgetRequirementValidator().validate(
            graph, BudgetRequirement(threshold_value=2000.0)
        )
        assert not errors

    def test_no_errors_when_total_cost_equals_limit(self) -> None:
        """Boundary: <= operator accepts exact equality."""
        graph: ArchitectureGraph = _graph(
            _compute_node("compute_1", 1000.0),
            _compute_node("compute_2", 1000.0),
        )
        errors = BudgetRequirementValidator().validate(
            graph, BudgetRequirement(threshold_value=2000.0)
        )
        assert not errors

    def test_budget_exceeded_reports_total_and_limit(self) -> None:
        graph: ArchitectureGraph = _graph(
            _compute_node("compute_1", 1500.0),
            _database_node("database_1", 2000.0),
        )
        errors = BudgetRequirementValidator().validate(
            graph, BudgetRequirement(threshold_value=3000.0)
        )

        assert len(errors) == 1
        error = errors[0]
        assert isinstance(error, BudgetExceededError)
        assert error.error_code == "BUDGET_EXCEEDED"
        assert error.total_monthly_cost_usd == EXPECTED_MONTHLY_COST
        assert error.budget_limit_usd == EXPECTED_ASSERT_ERROR_BUDGET_LIMIT_USD
        assert "3500.00" in error.message
        assert "3000.00" in error.message

    def test_client_nodes_are_excluded_from_total_cost(self) -> None:
        """ClientNode has no monthly_cost_usd: it must not contribute."""
        graph: ArchitectureGraph = _graph(
            ClientNode(identifier="web_client"),
            _compute_node("compute_1", 3000.0),
        )
        errors = BudgetRequirementValidator().validate(
            graph, BudgetRequirement(threshold_value=3000.0)
        )
        assert not errors


class _RecordingRequirementValidator(RequirementValidator[BudgetRequirement]):
    """Records calls and returns preset errors; used to test the dispatcher."""

    requirement_type = BudgetRequirement

    def __init__(self) -> None:
        self.received: list[BudgetRequirement] = []

    def validate(
        self, graph: ArchitectureGraph, requirement: BudgetRequirement
    ) -> list:
        del graph
        self.received.append(requirement)
        return []


class TestRequirementValidationDispatcher:
    def test_dispatches_requirement_to_matching_validator(self) -> None:
        validator = _RecordingRequirementValidator()
        dispatcher = RequirementValidationDispatcher([validator])
        requirement = BudgetRequirement(threshold_value=1000.0)
        dispatcher.validate(_graph(_compute_node("c", 100.0)), _scenario(requirement))
        assert validator.received == [requirement]

    def test_requirements_without_registered_validator_are_skipped(self) -> None:
        dispatcher = RequirementValidationDispatcher([_RecordingRequirementValidator()])
        # LatencyRequirement has no registered validator: no error, no crash.
        result = dispatcher.validate(
            _graph(_compute_node("c", 100.0)),
            _scenario(LatencyRequirement(threshold_value=300.0)),
        )
        assert not result.errors

    def test_multiple_same_type_requirements_dispatch_each_time(self) -> None:
        validator = _RecordingRequirementValidator()
        dispatcher = RequirementValidationDispatcher([validator])
        first = BudgetRequirement(threshold_value=1000.0)
        second = BudgetRequirement(threshold_value=2000.0)
        dispatcher.validate(_graph(_compute_node("c", 100.0)), _scenario(first, second))
        assert validator.received == [first, second]

    def test_empty_validator_set_is_a_no_op(self) -> None:
        dispatcher = RequirementValidationDispatcher([])
        result = dispatcher.validate(
            _graph(_compute_node("c", 100.0)),
            _scenario(BudgetRequirement(threshold_value=1000.0)),
        )
        assert not result.errors

    def test_duplicate_validator_for_same_type_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Duplicate RequirementValidator"):
            RequirementValidationDispatcher(
                [_RecordingRequirementValidator(), _RecordingRequirementValidator()]
            )

    def test_errors_are_aggregated_in_requirement_order(self) -> None:
        """Dispatcher must run every requirement and collect all errors."""
        validator = BudgetRequirementValidator()
        dispatcher = RequirementValidationDispatcher([validator])
        result = dispatcher.validate(
            _graph(_compute_node("c", 5000.0)),
            _scenario(
                BudgetRequirement(threshold_value=3000.0),
                BudgetRequirement(threshold_value=4000.0),
            ),
        )
        # Narrow through an isinstance filter: mypy then sees the concrete
        # error type inside the comprehension, and the test additionally
        # asserts that *every* produced error is a BudgetExceededError.
        budget_errors: list[BudgetExceededError] = [
            e for e in result.errors if isinstance(e, BudgetExceededError)
        ]
        assert (
            len(budget_errors) == len(result.errors) == EXPECTED_ERROR_COUNT
        )
        assert [e.budget_limit_usd for e in budget_errors] == [3000.0, 4000.0]

EXPECTED_ERROR_COUNT = 2
EXPECTED_ASSERT_ERROR_BUDGET_LIMIT_USD = 3000.0
EXPECTED_MONTHLY_COST = 3500.0
