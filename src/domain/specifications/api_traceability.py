"""Validate API coverage and unambiguous links to interaction scenarios."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from domain.exceptions.architecture_errors import ArchitectureValidationError
from domain.specifications.interfaces import ValidationResult

if TYPE_CHECKING:
    from collections.abc import Sequence
    from collections.abc import Set as AbstractSet

    from domain.models.api import ApiDesign, ApiOperation
    from domain.models.sequence import InteractionScenario


class ApiTraceabilityError(ArchitectureValidationError):
    """API references are missing, ambiguous or linked to another requirement."""

    error_code: str = "API_TRACEABILITY_ERROR"


class ApiTraceabilityValidator:
    """Require each API operation to identify its requirements and scenarios."""

    def validate(
        self,
        api: ApiDesign,
        sequences: Sequence[InteractionScenario],
        expected_requirement_ids: AbstractSet[str],
    ) -> ValidationResult:
        by_identifier: dict[str, list[InteractionScenario]] = defaultdict(list)
        for sequence in sequences:
            by_identifier[sequence.scenario_id].append(sequence)
        errors: list[ArchitectureValidationError] = [
            ApiTraceabilityError(f"Ambiguous scenario identifier: {identifier}")
            for identifier, matches in by_identifier.items()
            if len(matches) != 1
        ]
        covered: set[str] = set()
        for operation in api.operations:
            errors.extend(self._validate_operation(operation, by_identifier))
            covered.update(operation.requirement_ids)
        errors.extend(
            ApiTraceabilityError(f"No API operation covers requirement: {identifier}")
            for identifier in sorted(expected_requirement_ids - covered)
        )
        return ValidationResult(errors=errors)

    def _validate_operation(
        self,
        operation: ApiOperation,
        by_identifier: dict[str, list[InteractionScenario]],
    ) -> list[ArchitectureValidationError]:
        errors: list[ArchitectureValidationError] = []
        linked_requirements: set[str] = set()
        if not operation.requirement_ids or not operation.sequence_ids:
            errors.append(
                ApiTraceabilityError(
                    f"Operation {operation.operation_id} must reference both "
                    "requirements and interaction scenarios."
                )
            )
        for identifier in operation.sequence_ids:
            matches: list[InteractionScenario] = by_identifier.get(identifier, [])
            if len(matches) != 1:
                errors.append(
                    ApiTraceabilityError(
                        f"Operation {operation.operation_id} references an unknown "
                        f"or ambiguous scenario: {identifier}"
                    )
                )
                continue
            requirement_id: str = matches[0].requirement_identifier
            linked_requirements.add(requirement_id)
            if requirement_id not in operation.requirement_ids:
                errors.append(
                    ApiTraceabilityError(
                        f"Scenario {identifier} implements {requirement_id}, "
                        f"not the requirements of operation {operation.operation_id}."
                    )
                )
        missing: set[str] = set(operation.requirement_ids) - linked_requirements
        if missing:
            errors.append(
                ApiTraceabilityError(
                    f"Operation {operation.operation_id} has no matching scenario "
                    f"for requirements: {sorted(missing)}"
                )
            )
        return errors
