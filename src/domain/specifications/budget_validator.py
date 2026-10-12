"""Requirement validator: total monthly cost must satisfy the budget limit.

Pure domain logic: no I/O, no logging, no clock. Errors carry both the
observed total and the violated limit so the repair prompt can show the
model exactly how much it overshot.

Scope note: this validator knows only about a single BudgetRequirement.
Matching requirements to validators is the dispatcher's job
(RequirementValidationDispatcher), not this class's.
"""

from domain.exceptions.architecture_errors import (
    ArchitectureValidationError,
    BudgetExceededError,
)
from domain.models.nodes import CapacityNode
from domain.models.requirements import BudgetRequirement
from domain.models.topology import ArchitectureGraph
from domain.specifications.interfaces import RequirementValidator


class BudgetRequirementValidator(RequirementValidator[BudgetRequirement]):
    """Checks the total monthly cost of the topology against one budget.

    Client nodes carry no cost attribute and are naturally excluded:
    only CapacityNode subclasses contribute to the total.
    """

    requirement_type = BudgetRequirement

    def validate(
        self, graph: ArchitectureGraph, requirement: BudgetRequirement
    ) -> list[ArchitectureValidationError]:
        total_monthly_cost_usd: float = sum(
            float(node.monthly_cost_usd)
            for node in graph.nodes
            if isinstance(node, CapacityNode)
        )
        if requirement.is_met_requirement(total_monthly_cost_usd):
            return []
        return [
            BudgetExceededError(
                total_monthly_cost_usd=total_monthly_cost_usd,
                budget_limit_usd=requirement.threshold_value,
            )
        ]
