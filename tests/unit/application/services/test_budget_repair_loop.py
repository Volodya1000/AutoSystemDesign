"""Unit tests: a budget violation drives the design repair loop.

Exercises DesignGenerationService and RequirementValidationDispatcher with
a scripted fake designer; no LLM is involved.
"""

from collections.abc import Sequence

import pytest

from application.results import DesignGenerationResult, GenerationStatus
from application.services.design_generation_service import DesignGenerationService
from application.tasks import (
    DesignProposal,
    DesignTask,
    DesignTaskMode,
)
from application.usage import TokenUsage
from domain.exceptions.architecture_errors import BudgetExceededError
from domain.models.nodes import ComputeNode
from domain.models.requirements import BudgetRequirement
from domain.models.scenarios import DesignScenario, WorkloadProfile
from domain.models.topology import ArchitectureGraph
from domain.specifications.budget_validator import BudgetRequirementValidator
from domain.specifications.requirement_dispatch import (
    RequirementValidationDispatcher,
)
from domain.specifications.structural_validator import StructuralTopologyValidator

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


def _over_budget_graph() -> ArchitectureGraph:
    return ArchitectureGraph(nodes=[_compute_node("compute_1", 5000.0)], edges=[])


def _under_budget_graph() -> ArchitectureGraph:
    return ArchitectureGraph(nodes=[_compute_node("compute_1", 1000.0)], edges=[])


def _proposal(graph: ArchitectureGraph) -> DesignProposal:
    return DesignProposal(
        graph=graph,
        raw_content="{}",
        usage=TokenUsage(prompt_tokens=10, completion_tokens=10),
    )


class _ScriptedDesigner:
    """Designer stub returning a fixed sequence of proposals."""

    def __init__(self, script: Sequence[DesignProposal]) -> None:
        self._script: list[DesignProposal] = list(script)
        self.received_tasks: list[DesignTask] = []

    def propose(self, task: DesignTask) -> DesignProposal:
        self.received_tasks.append(task)
        return self._script.pop(0)


def _scenario() -> DesignScenario:
    return DesignScenario(
        identifier="budget_repair_test",
        description="Budget-driven repair loop",
        workload=WorkloadProfile(
            baseline_requests_per_second=10.0,
            peak_requests_per_second=20.0,
        ),
        requirements=[BudgetRequirement(threshold_value=3000.0)],
    )


def _budget_dispatcher() -> RequirementValidationDispatcher:
    """One dispatcher wired to the budget validator (single source of truth)."""
    return RequirementValidationDispatcher([BudgetRequirementValidator()])


def test_budget_violation_triggers_repair_attempt() -> None:
    """First answer is over budget, second fits: loop must succeed."""
    designer: _ScriptedDesigner = _ScriptedDesigner(
        [_proposal(_over_budget_graph()), _proposal(_under_budget_graph())]
    )
    service: DesignGenerationService = DesignGenerationService(
        designer=designer,  # type: ignore[arg-type]
        validators=[StructuralTopologyValidator()],
        max_attempts=2,
        scenario_validators=[_budget_dispatcher()],
    )

    result: DesignGenerationResult = service.generate(_scenario())

    assert result.status is GenerationStatus.SUCCEEDED
    assert len(result.attempts) == 2

    first_validation = result.attempts[0].validation
    assert first_validation is not None
    assert first_validation.has_error(BudgetExceededError)

    repair_task: DesignTask = designer.received_tasks[1]
    assert repair_task.mode is DesignTaskMode.REPAIR
    assert any(
        feedback.error_code == "BUDGET_EXCEEDED"
        for feedback in repair_task.validation_feedback
    )

    # Numeric context must reach the repair prompt: the observed total
    # (5000.0 from the graph) and the violated limit (3000.0 from the
    # scenario) both have to appear in the feedback messages.
    joined: str = " ".join(fb.message for fb in repair_task.validation_feedback)
    assert "5000.00" in joined
    assert "3000.00" in joined


def test_budget_failure_after_max_attempts_is_validation_failed() -> None:
    designer: _ScriptedDesigner = _ScriptedDesigner(
        [_proposal(_over_budget_graph()), _proposal(_over_budget_graph())]
    )
    service: DesignGenerationService = DesignGenerationService(
        designer=designer,  # type: ignore[arg-type]
        validators=[StructuralTopologyValidator()],
        max_attempts=2,
        scenario_validators=[_budget_dispatcher()],
    )

    result: DesignGenerationResult = service.generate(_scenario())

    assert result.status is GenerationStatus.VALIDATION_FAILED
    last_validation = result.attempts[-1].validation
    assert last_validation is not None
    assert last_validation.has_error(BudgetExceededError)
