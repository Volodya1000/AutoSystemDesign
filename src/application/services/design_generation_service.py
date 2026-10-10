"""Orchestration of the generate -> validate -> repair loop."""

from collections.abc import Sequence

from application.exceptions.generation_exceptions import DesignProposalParsingError
from application.protocols import ArchitectureDesigner
from application.results import DesignGenerationResult, GenerationAttempt
from application.tasks import (
    DesignProposal,
    DesignTask,
    DesignTaskMode,
    ValidationErrorFeedback,
)
from domain.models.scenarios import DesignScenario
from domain.models.topology import ArchitectureGraph
from domain.specifications.interfaces import BaseValidator, ValidationResult

_MIN_ATTEMPTS: int = 1
_MAX_ATTEMPTS: int = 10


def _build_parsing_repair_task(
    scenario: DesignScenario,
    parsing_error: DesignProposalParsingError,
) -> DesignTask:
    """Pure factory: repair task after an unparseable model output."""
    return DesignTask(
        scenario=scenario,
        mode=DesignTaskMode.REPAIR,
        previous_graph_payload=parsing_error.raw_content,
        parsing_failures=parsing_error.failure_details,
    )


def _build_validation_repair_task(
    scenario: DesignScenario,
    graph: ArchitectureGraph,
    validation: ValidationResult,
) -> DesignTask:
    """Pure factory: repair task after a structural validation failure."""
    feedback: list[ValidationErrorFeedback] = [
        ValidationErrorFeedback.from_error(error) for error in validation.errors
    ]
    return DesignTask(
        scenario=scenario,
        mode=DesignTaskMode.REPAIR,
        previous_graph_payload=graph.model_dump_json(),
        validation_feedback=feedback,
    )


class DesignGenerationService:
    """Runs the design loop: propose, validate, feed errors back for repair.

    Parsing failures are caught (tokens were spent and must be accounted
    for); infrastructure errors propagate to the caller. Multiple
    validators are all executed and their errors aggregated, so new
    validators (TMO, simulation) plug in without changing this class.
    """

    def __init__(
        self,
        designer: ArchitectureDesigner,
        validators: Sequence[BaseValidator],
        max_attempts: int,
    ) -> None:
        if not _MIN_ATTEMPTS <= max_attempts <= _MAX_ATTEMPTS:
            raise ValueError(
                f"max_attempts must be between {_MIN_ATTEMPTS} and {_MAX_ATTEMPTS}, "
                f"got {max_attempts}"
            )
        self._validators: tuple[BaseValidator, ...] = tuple(validators)
        if not self._validators:
            raise ValueError("At least one validator is required")
        self._designer = designer
        self._max_attempts = max_attempts

    def generate(self, scenario: DesignScenario) -> DesignGenerationResult:
        task: DesignTask = DesignTask(scenario=scenario, mode=DesignTaskMode.INITIAL)
        attempts: list[GenerationAttempt] = []

        for attempt_number in range(1, self._max_attempts + 1):
            try:
                proposal: DesignProposal = self._designer.propose(task)
            except DesignProposalParsingError as parsing_error:
                attempts.append(
                    GenerationAttempt(
                        attempt_number=attempt_number,
                        parsed=False,
                        graph=None,
                        validation=None,
                        usage=parsing_error.usage,
                    )
                )
                task = _build_parsing_repair_task(scenario, parsing_error)
                continue

            validation: ValidationResult = self._validate(proposal.graph)
            attempts.append(
                GenerationAttempt(
                    attempt_number=attempt_number,
                    parsed=True,
                    graph=proposal.graph,
                    validation=validation,
                    usage=proposal.usage,
                )
            )
            if validation.is_successful:
                break
            task = _build_validation_repair_task(scenario, proposal.graph, validation)

        return DesignGenerationResult(attempts=attempts)

    def _validate(self, graph: ArchitectureGraph) -> ValidationResult:
        """Runs every configured validator and aggregates their errors."""
        errors = [
            error
            for validator in self._validators
            for error in validator.validate(graph).errors
        ]
        return ValidationResult(errors=errors)
