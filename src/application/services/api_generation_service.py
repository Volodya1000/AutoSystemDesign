"""Application service orchestrating the propose -> validate -> repair loop for API design."""

from __future__ import annotations

import logging
from collections.abc import Mapping

from application.exceptions.generation_exceptions import DesignProposalParsingError
from shared.generation_limits import MAX_ATTEMPTS, MIN_ATTEMPTS
from application.protocols import ApiDesigner, ApiDesignValidatorPort
from application.results import ApiGenerationResult, GenerationAttempt
from application.tasks import (
    ApiDesignProposal,
    ApiDesignTask,
    DesignTaskMode,
    ValidationErrorFeedback,
)
from domain.models import DesignScenario
from domain.models.api import ApiDesign
from domain.models.sequence import InteractionScenario
from domain.models.topology import ArchitectureGraph
from domain.specifications.interfaces import ValidationResult


class ApiGenerationService:
    def __init__(
        self,
        designer: ApiDesigner,
        validator: ApiDesignValidatorPort,
        max_attempts: int,
    ) -> None:
        if not MIN_ATTEMPTS <= max_attempts <= MAX_ATTEMPTS:
            raise ValueError(
                f"max_attempts must be between {MIN_ATTEMPTS} and "
                f"{MAX_ATTEMPTS}, got {max_attempts}"
            )
        self._designer: ApiDesigner = designer
        self._validator: ApiDesignValidatorPort = validator
        self._max_attempts: int = max_attempts
        self.logger: logging.Logger = logging.getLogger(self.__class__.__name__)

    def generate(
        self,
        scenario: DesignScenario,
        graph: ArchitectureGraph,
        sequences: Mapping[str, InteractionScenario],
    ) -> ApiGenerationResult:
        expected_req_ids: set[str] = {
            req.identifier for req in scenario.functional_requirements
        }
        sequence_list: list[InteractionScenario] = list(sequences.values())

        task = ApiDesignTask(
            scenario=scenario,
            architecture_graph=graph,
            sequence_scenarios=sequence_list,
            mode=DesignTaskMode.INITIAL,
        )
        attempts: list[GenerationAttempt[ApiDesign]] = []

        for attempt_num in range(1, self._max_attempts + 1):
            try:
                proposal: ApiDesignProposal = self._designer.propose(task)
            except DesignProposalParsingError as pe:
                attempts.append(
                    GenerationAttempt[ApiDesign](
                        attempt_number=attempt_num,
                        parsed=False,
                        usage=pe.usage,
                        parsing_failures=pe.failure_details,
                    )
                )
                task = ApiDesignTask(
                    scenario=scenario,
                    architecture_graph=graph,
                    sequence_scenarios=sequence_list,
                    mode=DesignTaskMode.REPAIR,
                    previous_payload=pe.raw_content,
                    parsing_failures=pe.failure_details,
                )
                continue

            validation: ValidationResult = self._validator.validate(
                proposal.payload, graph, expected_req_ids
            )
            attempts.append(
                GenerationAttempt[ApiDesign](
                    attempt_number=attempt_num,
                    parsed=True,
                    payload=proposal.payload,
                    validation=validation,
                    usage=proposal.usage,
                    latency_seconds=proposal.latency_seconds,
                )
            )

            if validation.is_successful:
                return ApiGenerationResult(
                    attempts=attempts,
                    api_design=proposal.payload,
                )

            feedback = [
                ValidationErrorFeedback.from_error(err) for err in validation.errors
            ]
            task = ApiDesignTask(
                scenario=scenario,
                architecture_graph=graph,
                sequence_scenarios=sequence_list,
                mode=DesignTaskMode.REPAIR,
                previous_payload=proposal.payload.model_dump_json(),
                validation_feedback=feedback,
            )

        return ApiGenerationResult(attempts=attempts, api_design=None)
