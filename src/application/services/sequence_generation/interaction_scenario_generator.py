"""Generate and validate one interaction scenario for a functional requirement."""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.exceptions.generation_exceptions import DesignProposalParsingError
from application.results import GenerationAttempt
from application.tasks import (
    DesignTaskMode,
    SequenceInteractionTask,
    ValidationErrorFeedback,
)
from domain.models.sequence import InteractionScenario
from domain.specifications.interfaces import ValidationResult

if TYPE_CHECKING:
    from collections.abc import Sequence

    from application.protocols import SequenceDesignerProtocol
    from domain.exceptions.architecture_errors import ArchitectureValidationError
    from domain.models.functional import FunctionalRequirement
    from domain.models.roles import ProjectRolesCatalog
    from domain.models.topology import ArchitectureGraph
    from domain.specifications.sequence_validator import (
        SequenceScenarioValidatorProtocol,
    )


class InteractionScenarioGenerator:
    """Runs the propose -> validate -> repair loop for one requirement."""

    def __init__(
        self,
        designer: SequenceDesignerProtocol,
        validators: Sequence[SequenceScenarioValidatorProtocol],
        max_attempts: int,
    ) -> None:
        self._designer = designer
        self._validators = tuple(validators)
        self._max_attempts = max_attempts

    def generate(
        self,
        requirement: FunctionalRequirement,
        catalog: ProjectRolesCatalog,
        graph: ArchitectureGraph,
    ) -> tuple[
        list[GenerationAttempt[InteractionScenario]], InteractionScenario | None
    ]:
        task = SequenceInteractionTask(
            requirement=requirement,
            roles_catalog=catalog,
            architecture_graph=graph,
            mode=DesignTaskMode.INITIAL,
        )
        attempts: list[GenerationAttempt[InteractionScenario]] = []

        for attempt_num in range(1, self._max_attempts + 1):
            try:
                proposal = self._designer.propose_interaction(task)
            except DesignProposalParsingError as error:
                attempts.append(
                    GenerationAttempt[InteractionScenario](
                        attempt_number=attempt_num,
                        parsed=False,
                        usage=error.usage,
                        parsing_failures=error.failure_details,
                    )
                )
                task = SequenceInteractionTask(
                    requirement=requirement,
                    roles_catalog=catalog,
                    architecture_graph=graph,
                    mode=DesignTaskMode.REPAIR,
                    previous_payload=error.raw_content,
                    parsing_failures=error.failure_details,
                )
                continue

            interaction: InteractionScenario = proposal.payload.model_copy(
                update={"scenario_id": f"SC-{requirement.identifier}"}
            )
            validation = self._validate_scenario(
                interaction, catalog, graph, requirement.identifier
            )
            attempts.append(
                GenerationAttempt[InteractionScenario](
                    attempt_number=attempt_num,
                    parsed=True,
                    payload=interaction,
                    validation=validation,
                    usage=proposal.usage,
                    latency_seconds=proposal.latency_seconds,
                )
            )

            if validation.is_successful:
                return attempts, interaction

            feedback = [
                ValidationErrorFeedback.from_error(error) for error in validation.errors
            ]
            task = SequenceInteractionTask(
                requirement=requirement,
                roles_catalog=catalog,
                architecture_graph=graph,
                mode=DesignTaskMode.REPAIR,
                previous_payload=interaction.model_dump_json(),
                validation_feedback=feedback,
            )

        return attempts, None

    def _validate_scenario(
        self,
        scenario: InteractionScenario,
        catalog: ProjectRolesCatalog,
        graph: ArchitectureGraph,
        requirement_id: str,
    ) -> ValidationResult:
        errors: list[ArchitectureValidationError] = [
            error
            for validator in self._validators
            for error in validator.validate_scenario(
                scenario, catalog, graph, requirement_id
            ).errors
        ]
        return ValidationResult(errors=errors)
