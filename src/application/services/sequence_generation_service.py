"""Orchestration of the sequence-diagram generation stage."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from application.exceptions.generation_exceptions import DesignProposalParsingError
from application.protocols import SequenceDesigner
from application.results import (
    GenerationAttempt,
    SequenceGenerationResult,
    SequenceScenarioResult,
)
from application.tasks import (
    DesignTaskMode,
    SequenceInteractionTask,
    SequenceRoleTask,
    ValidationErrorFeedback,
)
from config.generation import (
    DEFAULT_SEQUENCE_PARALLELISM,
    MAX_ATTEMPTS,
    MIN_ATTEMPTS,
)
from domain.models.functional import FunctionalRequirement
from domain.models.roles import ProjectRolesCatalog
from domain.models.scenarios import DesignScenario
from domain.models.sequence import InteractionScenario
from domain.models.topology import ArchitectureGraph
from domain.specifications.interfaces import ValidationResult
from domain.specifications.sequence_validator import SequenceValidator


class SequenceGenerationService:
    """Generates the roles catalog and one interaction scenario per requirement.

    The service is deliberately small: it drives two repair loops (roles,
    then per-requirement interaction), delegating validation to a
    SequenceValidator and LLM transport to a SequenceDesigner. Partial
    results are preserved: a failing requirement does not discard the
    interactions that already succeeded.

    Interaction scenarios (per functional requirement) are generated in
    parallel via a thread pool when ``max_parallel_workers > 1``. Threads
    are safe here because the LLM client, the designer and the validator
    are all stateless after construction and the transport is I/O-bound.
    Set ``max_parallel_workers=1`` to get the legacy sequential behavior.
    """

    def __init__(
        self,
        designer: SequenceDesigner,
        validator: SequenceValidator,
        max_attempts: int,
        *,
        max_parallel_workers: int = DEFAULT_SEQUENCE_PARALLELISM,
    ) -> None:
        if not MIN_ATTEMPTS <= max_attempts <= MAX_ATTEMPTS:
            raise ValueError(
                f"max_attempts must be between {MIN_ATTEMPTS} and {MAX_ATTEMPTS}, "
                f"got {max_attempts}"
            )
        if max_parallel_workers < 1:
            raise ValueError(
                f"max_parallel_workers must be at least 1, got {max_parallel_workers}"
            )
        self._designer = designer
        self._validator = validator
        self._max_attempts = max_attempts
        self._max_parallel_workers = max_parallel_workers
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
                roles_attempts=roles_attempts,
                roles_catalog=None,
                scenarios_results={},
            )

        scenarios_results = self._generate_all_interactions(
            scenario.functional_requirements, catalog, graph
        )

        return SequenceGenerationResult(
            roles_attempts=roles_attempts,
            roles_catalog=catalog,
            scenarios_results=scenarios_results,
        )

    # ------------------------------------------------------------------ helpers

    def _generate_all_interactions(
        self,
        requirements: list[FunctionalRequirement],
        catalog: ProjectRolesCatalog,
        graph: ArchitectureGraph,
    ) -> dict[str, SequenceScenarioResult]:
        """Dispatches per-requirement generation sequentially or in parallel."""
        if len(requirements) <= 1 or self._max_parallel_workers <= 1:
            return self._generate_interactions_sequential(requirements, catalog, graph)
        return self._generate_interactions_parallel(requirements, catalog, graph)

    def _generate_interactions_sequential(
        self,
        requirements: list[FunctionalRequirement],
        catalog: ProjectRolesCatalog,
        graph: ArchitectureGraph,
    ) -> dict[str, SequenceScenarioResult]:
        scenarios_results: dict[str, SequenceScenarioResult] = {}
        for req in requirements:
            self.logger.info(
                "Generating sequence scenario for requirement: %s", req.identifier
            )
            attempts, interaction = self._generate_interaction(req, catalog, graph)
            scenarios_results[req.identifier] = SequenceScenarioResult(
                attempts=attempts,
                interaction_scenario=interaction,
            )
        return scenarios_results

    def _generate_interactions_parallel(
        self,
        requirements: list[FunctionalRequirement],
        catalog: ProjectRolesCatalog,
        graph: ArchitectureGraph,
    ) -> dict[str, SequenceScenarioResult]:
        max_workers = min(len(requirements), self._max_parallel_workers)
        self.logger.info(
            "Generating %d sequence scenarios in parallel (max_workers=%d)",
            len(requirements),
            max_workers,
        )

        results_by_req: dict[str, SequenceScenarioResult] = {}
        with ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="seq-gen"
        ) as executor:
            futures = {
                executor.submit(
                    self._generate_interaction_with_logging, req, catalog, graph
                ): req
                for req in requirements
            }
            for future in as_completed(futures):
                req = futures[future]
                attempts, interaction = future.result()
                results_by_req[req.identifier] = SequenceScenarioResult(
                    attempts=attempts,
                    interaction_scenario=interaction,
                )
                self.logger.info(
                    "Finished sequence scenario for requirement: %s (%s)",
                    req.identifier,
                    "success" if interaction is not None else "no scenario",
                )

        # Rebuild in requirement order for deterministic downstream behavior.
        return {req.identifier: results_by_req[req.identifier] for req in requirements}

    def _generate_interaction_with_logging(
        self,
        req: FunctionalRequirement,
        catalog: ProjectRolesCatalog,
        graph: ArchitectureGraph,
    ) -> tuple[
        list[GenerationAttempt[InteractionScenario]], InteractionScenario | None
    ]:
        self.logger.info(
            "Generating sequence scenario for requirement: %s", req.identifier
        )
        return self._generate_interaction(req, catalog, graph)

    # ------------------------------------------------------------------- roles

    def _generate_roles(
        self, scenario: DesignScenario
    ) -> tuple[
        list[GenerationAttempt[ProjectRolesCatalog]],
        ProjectRolesCatalog | None,
    ]:
        task = SequenceRoleTask(scenario=scenario, mode=DesignTaskMode.INITIAL)
        attempts: list[GenerationAttempt[ProjectRolesCatalog]] = []

        for attempt_num in range(1, self._max_attempts + 1):
            try:
                proposal = self._designer.propose_roles(task)
            except DesignProposalParsingError as pe:
                attempts.append(
                    GenerationAttempt[ProjectRolesCatalog](
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
                ValidationErrorFeedback.from_error(e) for e in validation.errors
            ]
            task = SequenceRoleTask(
                scenario=scenario,
                mode=DesignTaskMode.REPAIR,
                previous_payload=proposal.payload.model_dump_json(),
                validation_feedback=feedback,
            )

        return attempts, None

    # -------------------------------------------------------------- interaction

    def _generate_interaction(
        self,
        req: FunctionalRequirement,
        catalog: ProjectRolesCatalog,
        graph: ArchitectureGraph,
    ) -> tuple[
        list[GenerationAttempt[InteractionScenario]],
        InteractionScenario | None,
    ]:
        task = SequenceInteractionTask(
            requirement=req,
            roles_catalog=catalog,
            architecture_graph=graph,
            mode=DesignTaskMode.INITIAL,
        )
        attempts: list[GenerationAttempt[InteractionScenario]] = []

        for attempt_num in range(1, self._max_attempts + 1):
            try:
                proposal = self._designer.propose_interaction(task)
            except DesignProposalParsingError as pe:
                attempts.append(
                    GenerationAttempt[InteractionScenario](
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
                GenerationAttempt[InteractionScenario](
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
