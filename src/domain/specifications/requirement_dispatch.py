"""Dispatcher: routes scenario requirements to typed RequirementValidators.

Single point that knows how requirements are matched to validators. Each
concrete RequirementValidator only sees the requirement it was written
for (narrow interface, ISP); the dispatcher owns the lookup logic (SRP).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from domain.exceptions.model_validation_errors import (
    ModelValidationCode,
    ModelValidationError,
)
from domain.models.requirement_coverage import (
    RequirementAssessment,
    RequirementCheckReason,
    RequirementCheckStatus,
    requirement_identifier,
)
from domain.models.requirements import (
    AvailabilityRequirement,
    LatencyRequirement,
    QueueSizePercentileRequirement,
    ResourceUtilizationRequirement,
)
from domain.specifications.interfaces import (
    RequirementValidator,
    ScenarioValidator,
    ValidationResult,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain.exceptions.architecture_errors import ArchitectureValidationError
    from domain.models.base_constraints import BaseRequirement
    from domain.models.scenarios import DesignScenario
    from domain.models.topology import ArchitectureGraph


class RequirementValidationDispatcher(ScenarioValidator):
    """Adapts a set of RequirementValidator instances into one ScenarioValidator.

    Requirements without a registered validator produce non-blocking,
    traceable NOT_EVALUATED assessments. Validation errors still drive repair.
    """

    def __init__(self, validators: Sequence[RequirementValidator[Any]]) -> None:
        by_type: dict[type[BaseRequirement], RequirementValidator[Any]] = {}
        for validator in validators:
            requirement_type: type[BaseRequirement] = validator.requirement_type
            if requirement_type in by_type:
                raise ModelValidationError(
                    ModelValidationCode.DUPLICATE_REQUIREMENT_VALIDATOR,
                    requirement_type=requirement_type.__name__,
                )
            by_type[requirement_type] = validator
        self._by_type: dict[type[BaseRequirement], RequirementValidator[Any]] = by_type

    def validate(
        self, graph: ArchitectureGraph, scenario: DesignScenario
    ) -> ValidationResult:
        """Run each distinct requirement occurrence, preserving its identity."""
        errors: list[ArchitectureValidationError] = []
        assessments: list[RequirementAssessment] = []
        for index, requirement in enumerate(scenario.requirements):
            identifier = requirement_identifier(index)
            kind = getattr(
                requirement, "type_identifier", type(requirement).__name__
            )
            validator = self._by_type.get(type(requirement))
            if validator is None:
                assessments.append(
                    RequirementAssessment.not_evaluated(
                        identifier=identifier,
                        kind=kind,
                        reason=_unsupported_reason(
                            requirement,
                            workload_missing=scenario.workload is None,
                        ),
                    )
                )
                continue

            violations = validator.validate(graph, requirement)
            errors.extend(violations)
            assessments.append(
                RequirementAssessment(
                    requirement_identifier=identifier,
                    type_identifier=kind,
                    status=(
                        RequirementCheckStatus.VIOLATED
                        if violations
                        else RequirementCheckStatus.SATISFIED
                    ),
                    validator_identifier=type(validator).__name__,
                )
            )
        return ValidationResult(
            errors=errors, requirement_assessments=assessments
        )


def _unsupported_reason(
    requirement: BaseRequirement, *, workload_missing: bool
) -> RequirementCheckReason:
    """Use typed requirement classes, never heuristic name comparisons."""
    load_dependent = (
        LatencyRequirement,
        QueueSizePercentileRequirement,
        ResourceUtilizationRequirement,
    )
    if workload_missing and isinstance(requirement, load_dependent):
        return RequirementCheckReason.MISSING_WORKLOAD
    if isinstance(requirement, (LatencyRequirement, QueueSizePercentileRequirement)):
        return RequirementCheckReason.PERCENTILE_UNMODELED
    if isinstance(requirement, ResourceUtilizationRequirement):
        return RequirementCheckReason.TARGET_SCOPE_UNSPECIFIED
    if isinstance(requirement, AvailabilityRequirement):
        return RequirementCheckReason.RELIABILITY_MODEL_UNAVAILABLE
    return RequirementCheckReason.NO_VALIDATOR
