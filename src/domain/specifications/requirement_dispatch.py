"""Dispatcher: routes scenario requirements to typed RequirementValidators.

Single point that knows how requirements are matched to validators. Each
concrete RequirementValidator only sees the requirement it was written
for (narrow interface, ISP); the dispatcher owns the lookup logic (SRP).
"""

from collections.abc import Sequence
from typing import Any

from domain.exceptions.architecture_errors import ArchitectureValidationError
from domain.models.base_constraints import BaseRequirement
from domain.models.scenarios import DesignScenario
from domain.models.topology import ArchitectureGraph
from domain.specifications.interfaces import (
    RequirementValidator,
    ScenarioValidator,
    ValidationResult,
)


class RequirementValidationDispatcher(ScenarioValidator):
    """Adapts a set of RequirementValidator instances into one ScenarioValidator.

    Requirements without a registered validator are silently skipped, so
    partially supported scenarios keep working: adding support for a new
    requirement kind means registering one more validator, nothing else.
    """

    def __init__(self, validators: Sequence[RequirementValidator[Any]]) -> None:
        by_type: dict[type[BaseRequirement], RequirementValidator[Any]] = {}
        for validator in validators:
            requirement_type: type[BaseRequirement] = validator.requirement_type
            if requirement_type in by_type:
                raise ValueError(
                    f"Duplicate RequirementValidator for {requirement_type.__name__}"
                )
            by_type[requirement_type] = validator
        self._by_type: dict[type[BaseRequirement], RequirementValidator[Any]] = by_type

    def validate(
        self, graph: ArchitectureGraph, scenario: DesignScenario
    ) -> ValidationResult:
        """Runs every requirement through its registered validator, in order."""
        errors: list[ArchitectureValidationError] = []
        for requirement in scenario.requirements:
            validator = self._by_type.get(type(requirement))
            if validator is None:
                continue
            errors.extend(validator.validate(graph, requirement))
        return ValidationResult(errors=errors)
