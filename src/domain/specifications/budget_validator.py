"""Scenario validator: total monthly cost must satisfy the budget limits.

Pure domain logic: no I/O, no logging, no clock. Errors carry both the
observed total and the violated limit so the repair prompt can show the
model exactly how much it overshot.
"""

from domain.exceptions.architecture_errors import (
    ArchitectureValidationError,
    BudgetExceededError,
)
from domain.models.nodes import CapacityNode
from domain.models.requirements import BudgetRequirement
from domain.models.scenarios import DesignScenario
from domain.models.topology import ArchitectureGraph
from domain.specifications.interfaces import ScenarioValidator, ValidationResult


class BudgetValidator(ScenarioValidator):
    """Checks the total monthly cost of the topology against the budget.

    A scenario may declare zero, one or several BudgetRequirement entries.
    Every violated requirement produces its own error so the repair loop
    can point at each constraint separately. A scenario without budget
    requirements is a no-op, which keeps older scenarios working.

    Client nodes carry no cost attribute and are naturally excluded from
    the total: only CapacityNode subclasses contribute.
    """

    def validate(
        self, graph: ArchitectureGraph, scenario: DesignScenario
    ) -> ValidationResult:
        budget_requirements: list[BudgetRequirement] = [
            requirement
            for requirement in scenario.requirements
            if isinstance(requirement, BudgetRequirement)
        ]
        if not budget_requirements:
            return ValidationResult(errors=[])

        total_monthly_cost_usd: float = sum(
            float(node.monthly_cost_usd)
            for node in graph.nodes
            if isinstance(node, CapacityNode)
        )

        errors: list[ArchitectureValidationError] = [
            BudgetExceededError(
                total_monthly_cost_usd=total_monthly_cost_usd,
                budget_limit_usd=requirement.threshold_value,
            )
            for requirement in budget_requirements
            if not requirement.is_met_requirement(total_monthly_cost_usd)
        ]
        return ValidationResult(errors=errors)
