import logging

from application.exceptions.generation_exceptions import DesignProposalParsingError
from application.protocols import SequenceDesigner
from application.results import (
    GenerationAttempt,
    SequenceGenerationResult,
    SequenceScenarioResult,
)
from application.services.design_generation_service import _MAX_ATTEMPTS, _MIN_ATTEMPTS
from application.tasks import (
    DesignTaskMode,
    SequenceInteractionTask,
    SequenceRoleTask,
    ValidationErrorFeedback,
)
from domain.models.functional import FunctionalRequirement
from domain.models.roles import ProjectRolesCatalog
from domain.models.scenarios import DesignScenario
from domain.models.sequence import InteractionScenario
from domain.models.topology import ArchitectureGraph
from domain.specifications.interfaces import ValidationResult
from domain.specifications.sequence_validator import SequenceValidator


class SequenceGenerationService:
    def __init__(
        self,
        designer: SequenceDesigner,
        validator: SequenceValidator,
        max_attempts: int,
    ) -> None:
        if not _MIN_ATTEMPTS <= max_attempts <= _MAX_ATTEMPTS:
            raise ValueError(
                f"max_attempts must be between {_MIN_ATTEMPTS} and {_MAX_ATTEMPTS}"
            )
        self._designer = designer
        self._validator = validator
        self._max_attempts = max_attempts
        self.logger = logging.getLogger(self.__class__.__name__)

    def generate(
        self, scenario: DesignScenario, graph: ArchitectureGraph
    ) -> SequenceGenerationResult:
        if not scenario.functional_requirements:
            self.logger.warning(
                "No functional requirements provided. Skipping sequence generation."
            )
            return SequenceGenerationResult(
                roles_attempts=[], roles_catalog=None, scenarios_results={}
            )

        roles_attempts, catalog = self._generate_roles(scenario)
        if catalog is None:
            self.logger.error(
                "Failed to generate Roles Catalog. Aborting sequence generation."
            )
            return SequenceGenerationResult(
                roles_attempts=roles_attempts, roles_catalog=None, scenarios_results={}
            )

        scenarios_results: dict[str, SequenceScenarioResult] = {}
        for req in scenario.functional_requirements:
            self.logger.info(
                "Generating sequence scenario for requirement: %s", req.identifier
            )
            attempts, interaction = self._generate_interaction(req, catalog, graph)
            scenarios_results[req.identifier] = SequenceScenarioResult(
                attempts=attempts,
                interaction_scenario=interaction,
            )

        return SequenceGenerationResult(
            roles_attempts=roles_attempts,
            roles_catalog=catalog,
            scenarios_results=scenarios_results,
        )

    def _generate_roles(
        self, scenario: DesignScenario
    ) -> tuple[list[GenerationAttempt], ProjectRolesCatalog | None]:
        task = SequenceRoleTask(scenario=scenario, mode=DesignTaskMode.INITIAL)
        attempts: list[GenerationAttempt] = []

        for attempt_num in range(1, self._max_attempts + 1):
            try:
                proposal = self._designer.propose_roles(task)
            except DesignProposalParsingError as pe:
                attempts.append(
                    GenerationAttempt(
                        attempt_number=attempt_num,
                        parsed=False,
                        usage=pe.usage,
                        parsing_failures=pe.failure_details,
                    )
                )
                task = SequenceRoleTask(
                    scenario=scenario,
                    mode=DesignTaskMode.REPAIR,
                    previous_payload=pe.raw_content,
                    parsing_failures=pe.failure_details,
                )
                continue

            validation: ValidationResult = self._validator.validate_catalog(
                proposal.payload
            )
            attempts.append(
                GenerationAttempt(
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
                ValidationErrorFeedback.from_error(e) for e in validation.errors
            ]
            task = SequenceRoleTask(
                scenario=scenario,
                mode=DesignTaskMode.REPAIR,
                previous_payload=proposal.payload.model_dump_json(),
                validation_feedback=feedback,
            )

        return attempts, None

    def _generate_interaction(
        self,
        req: FunctionalRequirement,
        catalog: ProjectRolesCatalog,
        graph: ArchitectureGraph,
    ) -> tuple[list[GenerationAttempt], InteractionScenario | None]:
        task = SequenceInteractionTask(
            requirement=req,
            roles_catalog=catalog,
            architecture_graph=graph,
            mode=DesignTaskMode.INITIAL,
        )
        attempts: list[GenerationAttempt] = []

        for attempt_num in range(1, self._max_attempts + 1):
            try:
                proposal = self._designer.propose_interaction(task)
            except DesignProposalParsingError as pe:
                attempts.append(
                    GenerationAttempt(
                        attempt_number=attempt_num,
                        parsed=False,
                        usage=pe.usage,
                        parsing_failures=pe.failure_details,
                    )
                )
                task = SequenceInteractionTask(
                    requirement=req,
                    roles_catalog=catalog,
                    architecture_graph=graph,
                    mode=DesignTaskMode.REPAIR,
                    previous_payload=pe.raw_content,
                    parsing_failures=pe.failure_details,
                )
                continue

            validation: ValidationResult = self._validator.validate_scenario(
                proposal.payload, catalog, graph, req.identifier
            )
            attempts.append(
                GenerationAttempt(
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
                ValidationErrorFeedback.from_error(e) for e in validation.errors
            ]
            task = SequenceInteractionTask(
                requirement=req,
                roles_catalog=catalog,
                architecture_graph=graph,
                mode=DesignTaskMode.REPAIR,
                previous_payload=proposal.payload.model_dump_json(),
                validation_feedback=feedback,
            )

        return attempts, None
