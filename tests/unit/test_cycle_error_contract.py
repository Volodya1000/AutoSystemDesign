"""Regression tests for cycle-only suppression in workload validators."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest

from application.results import GenerationStatus
from application.services.design_generation_service import DesignGenerationService
from application.tasks import DesignProposal, DesignTask
from application.usage import TokenUsage
from domain.exceptions.architecture_errors import (
    BudgetExceededError,
    CyclicDependencyError,
)
from domain.exceptions.model_validation_errors import (
    ModelValidationCode,
    ModelValidationError,
)
from domain.models.enums import NodeType
from domain.models.requirements import BudgetRequirement
from domain.models.scenarios import DesignScenario, WorkloadProfile
from domain.models.topology import ArchitectureGraph
from domain.specifications import capacity_validator, latency_validator
from domain.specifications.budget_validator import BudgetRequirementValidator
from domain.specifications.capacity_validator import CapacitySaturationValidator
from domain.specifications.requirement_dispatch import (
    RequirementValidationDispatcher,
)
from domain.specifications.structural_validator import StructuralTopologyValidator
from tests.factories import create_test_edge, create_test_node

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType


pytestmark = pytest.mark.unit


def _scenario() -> DesignScenario:
    """Build a scenario with a real workload for both validators."""
    return DesignScenario(
        identifier="validator_error_contract",
        description="Test error handling in workload validators",
        workload=WorkloadProfile(
            baseline_requests_per_second=10.0,
            peak_requests_per_second=20.0,
        ),
        requirements=[],
    )


def _valid_graph() -> ArchitectureGraph:
    """Build an ordinary acyclic graph."""
    return ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            create_test_node("compute", NodeType.COMPUTE),
        ],
        edges=[create_test_edge("client", "compute")],
    )


@pytest.mark.parametrize(
    ("module", "operation"),
    [
        (capacity_validator, CapacitySaturationValidator().validate),
        (latency_validator, latency_validator.compute_critical_path),
    ],
)
@pytest.mark.parametrize(
    "error",
    [
        ValueError("Unexpected numeric calculation failure"),
        ModelValidationError(ModelValidationCode.WORKLOAD_PEAK_BELOW_BASELINE),
    ],
)
def test_non_cycle_value_errors_are_not_suppressed(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    operation: Callable[[ArchitectureGraph, DesignScenario], object],
    error: ValueError,
) -> None:
    """Propagate unexpected errors from capacity or critical-path calculations."""
    monkeypatch.setattr(
        module,
        "compute_node_incoming_rps",
        Mock(side_effect=error),
    )
    with pytest.raises(type(error), match=re.escape(str(error))) as caught:
        operation(_valid_graph(), _scenario())
    assert caught.value is error


class _FixedGraphDesigner:
    """Return the same graph without calling an LLM."""

    def __init__(self, graph: ArchitectureGraph) -> None:
        self._graph = graph

    def propose(self, task: DesignTask) -> DesignProposal:
        del task
        return DesignProposal(
            graph=self._graph,
            raw_content="{}",
            usage=TokenUsage(),
        )


def test_cycle_is_reported_once_and_other_errors_are_aggregated() -> None:
    """Preserve one structural cycle error plus independent budget feedback."""
    graph = ArchitectureGraph(
        nodes=[
            create_test_node("compute_1", NodeType.COMPUTE),
            create_test_node("compute_2", NodeType.COMPUTE),
        ],
        edges=[
            create_test_edge("compute_1", "compute_2"),
            create_test_edge("compute_2", "compute_1"),
        ],
    )
    scenario = DesignScenario(
        identifier="cycle_with_budget_violation",
        description="Cycle and an independent budget violation",
        workload=WorkloadProfile(
            baseline_requests_per_second=10.0,
            peak_requests_per_second=20.0,
        ),
        requirements=[BudgetRequirement(threshold_value=10.0)],
    )
    service = DesignGenerationService(
        designer=_FixedGraphDesigner(graph),
        validators=[StructuralTopologyValidator()],
        scenario_validators=[
            RequirementValidationDispatcher([BudgetRequirementValidator()]),
            CapacitySaturationValidator(),
        ],
        max_attempts=1,
    )

    result = service.generate(scenario)

    assert result.status is GenerationStatus.VALIDATION_FAILED
    validation = result.attempts[0].validation
    assert validation is not None
    assert sum(isinstance(err, CyclicDependencyError) for err in validation.errors) == 1
    assert sum(isinstance(err, BudgetExceededError) for err in validation.errors) == 1
