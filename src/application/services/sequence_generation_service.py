import logging

from application.exceptions.generation_exceptions import DesignProposalParsingError
from application.results import (
    SequenceGenerationAttempt,
    SequenceGenerationResult,
)
from application.tasks import (
    DesignTaskMode,
    SequenceContextTask,
    SequenceInteractionTask,
    ValidationErrorFeedback,
)
from domain.models.scenarios import DesignScenario
from domain.models.sequence import InteractionScenario
from domain.models.system_design import SystemContextOutput, SystemDesignOutput
from domain.models.topology import ArchitectureGraph
from domain.specifications.sequence_validator import SequenceValidator


class SequenceGenerationService:
    def __init__(
        self, designer, validator: SequenceValidator, max_attempts: int
    ) -> None:
        if not 1 <= max_attempts <= 10:
            raise ValueError(
                f"max_attempts must be between 1 and 10, got {max_attempts}"
            )
        self._designer = designer
        self._validator = validator
        self._max_attempts = max_attempts
        self.logger = logging.getLogger(self.__class__.__name__)

    def generate(
        self, scenario: DesignScenario, graph: ArchitectureGraph
    ) -> SequenceGenerationResult:
        all_attempts = []

        context_output = self._generate_context(scenario, graph, all_attempts)
        if context_output is None:
            return SequenceGenerationResult(attempts=all_attempts)

        interaction_scenarios = []
        for req in context_output.functional_requirements:
            interaction_scenario = self._generate_interaction(
                scenario, graph, req, context_output.roles_catalog, all_attempts
            )
            if interaction_scenario is not None:
                interaction_scenarios.append(interaction_scenario)
            else:
                self.logger.warning(
                    "Failed to generate interaction for requirement %s. Skipping.",
                    req.identifier,
                )

        system_design = SystemDesignOutput(
            functional_requirements=context_output.functional_requirements,
            roles_catalog=context_output.roles_catalog,
            interaction_scenarios=interaction_scenarios,
        )

        last_attempt = all_attempts[-1]
        all_attempts[-1] = last_attempt.model_copy(
            update={"system_design": system_design}
        )

        return SequenceGenerationResult(attempts=all_attempts)

    def _generate_context(
        self, scenario: DesignScenario, graph: ArchitectureGraph, all_attempts: list
    ) -> SystemContextOutput | None:
        task = SequenceContextTask(
            scenario=scenario, architecture_graph=graph, mode=DesignTaskMode.INITIAL
        )
        for attempt_number in range(1, self._max_attempts + 1):
            try:
                proposal = self._designer.propose_context(task)
                all_attempts.append(
                    SequenceGenerationAttempt(
                        attempt_number=attempt_number,
                        parsed=True,
                        validation=None,
                        usage=proposal.usage,
                        latency_seconds=proposal.latency_seconds,
                    )
                )
                return proposal.context_output
            except DesignProposalParsingError as parsing_error:
                all_attempts.append(
                    SequenceGenerationAttempt(
                        attempt_number=attempt_number,
                        parsed=False,
                        usage=parsing_error.usage,
                        parsing_failures=parsing_error.failure_details,
                    )
                )
                task = SequenceContextTask(
                    scenario=scenario,
                    architecture_graph=graph,
                    mode=DesignTaskMode.REPAIR,
                    previous_payload=parsing_error.raw_content,
                    parsing_failures=parsing_error.failure_details,
                )
        return None

    def _generate_interaction(
        self,
        scenario: DesignScenario,
        graph: ArchitectureGraph,
        req,
        roles,
        all_attempts: list,
    ) -> InteractionScenario | None:
        task = SequenceInteractionTask(
            scenario=scenario,
            architecture_graph=graph,
            requirement=req,
            roles_catalog=roles,
            mode=DesignTaskMode.INITIAL,
        )
        for attempt_number in range(1, self._max_attempts + 1):
            try:
                proposal = self._designer.propose_interaction(task)
            except DesignProposalParsingError as parsing_error:
                all_attempts.append(
                    SequenceGenerationAttempt(
                        attempt_number=attempt_number,
                        parsed=False,
                        usage=parsing_error.usage,
                        parsing_failures=parsing_error.failure_details,
                    )
                )
                task = SequenceInteractionTask(
                    scenario=scenario,
                    architecture_graph=graph,
                    requirement=req,
                    roles_catalog=roles,
                    mode=DesignTaskMode.REPAIR,
                    previous_payload=parsing_error.raw_content,
                    parsing_failures=parsing_error.failure_details,
                )
                continue

            mock_design = SystemDesignOutput(
                functional_requirements=[req],
                roles_catalog=roles,
                interaction_scenarios=[proposal.interaction_scenario],
            )
            validation = self._validator.validate(mock_design, graph)

            all_attempts.append(
                SequenceGenerationAttempt(
                    attempt_number=attempt_number,
                    parsed=True,
                    validation=validation,
                    usage=proposal.usage,
                    latency_seconds=proposal.latency_seconds,
                )
            )

            if validation.is_successful:
                return proposal.interaction_scenario

            feedback = [
                ValidationErrorFeedback.from_error(error) for error in validation.errors
            ]
            task = SequenceInteractionTask(
                scenario=scenario,
                architecture_graph=graph,
                requirement=req,
                roles_catalog=roles,
                mode=DesignTaskMode.REPAIR,
                previous_payload=proposal.interaction_scenario.model_dump_json(),
                validation_feedback=feedback,
            )
        return None
