"""Generate and validate the project-wide business roles catalog."""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.exceptions.generation_exceptions import DesignProposalParsingError
from application.results import GenerationAttempt
from application.tasks import DesignTaskMode, SequenceRoleTask, ValidationErrorFeedback
from domain.models.roles import ProjectRolesCatalog
from domain.specifications.interfaces import ValidationResult

if TYPE_CHECKING:
    from collections.abc import Sequence

    from application.protocols import SequenceDesigner
    from domain.exceptions.architecture_errors import ArchitectureValidationError
    from domain.models.scenarios import DesignScenario
    from domain.specifications.sequence_validator import SequenceCatalogValidator


class RolesCatalogGenerator:
    """Runs the propose -> validate -> repair loop for a roles catalog."""

    def __init__(
        self,
        designer: SequenceDesigner,
        validators: Sequence[SequenceCatalogValidator],
        max_attempts: int,
    ) -> None:
        self._designer = designer
        self._validators = tuple(validators)
        self._max_attempts = max_attempts

    def generate(
        self, scenario: DesignScenario
    ) -> tuple[
        list[GenerationAttempt[ProjectRolesCatalog]], ProjectRolesCatalog | None
    ]:
        task = SequenceRoleTask(scenario=scenario, mode=DesignTaskMode.INITIAL)
        attempts: list[GenerationAttempt[ProjectRolesCatalog]] = []

        for attempt_num in range(1, self._max_attempts + 1):
            try:
                proposal = self._designer.propose_roles(task)
            except DesignProposalParsingError as error:
                attempts.append(
                    GenerationAttempt[ProjectRolesCatalog](
                        attempt_number=attempt_num,
                        parsed=False,
                        usage=error.usage,
                        parsing_failures=error.failure_details,
                    )
                )
                task = SequenceRoleTask(
                    scenario=scenario,
                    mode=DesignTaskMode.REPAIR,
                    previous_payload=error.raw_content,
                    parsing_failures=error.failure_details,
                )
                continue

            validation = self._validate_catalog(proposal.payload)
            attempts.append(
                GenerationAttempt[ProjectRolesCatalog](
                    attempt_number=attempt_num,
                    parsed=True,
                    payload=proposal.payload,
                    validation=validation,
                    usage=proposal.usage,
                    latency_seconds=proposal.latency_seconds,
                )
            )

            if validation.is_successful:
                return attempts, proposal.payload

            feedback = [
                ValidationErrorFeedback.from_error(error) for error in validation.errors
            ]
            task = SequenceRoleTask(
                scenario=scenario,
                mode=DesignTaskMode.REPAIR,
                previous_payload=proposal.payload.model_dump_json(),
                validation_feedback=feedback,
            )

        return attempts, None

    def _validate_catalog(self, catalog: ProjectRolesCatalog) -> ValidationResult:
        errors: list[ArchitectureValidationError] = [
            error
            for validator in self._validators
            for error in validator.validate_catalog(catalog).errors
        ]
        return ValidationResult(errors=errors)
