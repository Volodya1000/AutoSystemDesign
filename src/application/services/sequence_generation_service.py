"""Orchestration of the sequence-diagram generation stage."""

import logging
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed

from application.protocols import SequenceDesigner
from application.results import (
    GenerationAttempt,
    SequenceGenerationResult,
    SequenceScenarioResult,
)
from application.services.sequence_generation.interaction_scenario_generator import (
    InteractionScenarioGenerator,
)
from application.services.sequence_generation.roles_catalog_generator import (
    RolesCatalogGenerator,
)
from application.generation_limits import (
    DEFAULT_SEQUENCE_PARALLELISM,
    MAX_ATTEMPTS,
    MIN_ATTEMPTS,
)
from domain.models.functional import FunctionalRequirement
from domain.models.roles import ProjectRolesCatalog
from domain.models.scenarios import DesignScenario
from domain.models.sequence import InteractionScenario
from domain.models.topology import ArchitectureGraph
from domain.specifications.sequence_validator import (
    SequenceCatalogValidator,
    SequenceScenarioValidator,
)


class SequenceGenerationService:
    """Generates the roles catalog and one interaction scenario per requirement.

    The service coordinates focused generators for the roles catalog and
    per-requirement interactions. It owns dispatch and result aggregation;
    the focused generators own their respective propose -> validate -> repair
    loops. Partial results are preserved: a failing requirement does not
    discard the interactions that already succeeded.

    Interaction scenarios (per functional requirement) are generated in
    parallel via a thread pool when ``max_parallel_workers > 1``. Threads
    are safe here because the LLM client, the designer and the validators
    are all stateless after construction and the transport is I/O-bound.
    Set ``max_parallel_workers=1`` to get the legacy sequential behavior.
    """

    def __init__(
        self,
        designer: SequenceDesigner,
        catalog_validators: Sequence[SequenceCatalogValidator],
        scenario_validators: Sequence[SequenceScenarioValidator],
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
        catalog_validator_tuple: tuple[SequenceCatalogValidator, ...] = tuple(
            catalog_validators
        )
        if not catalog_validator_tuple:
            raise ValueError("At least one catalog validator is required")
        scenario_validator_tuple: tuple[SequenceScenarioValidator, ...] = tuple(
            scenario_validators
        )
        if not scenario_validator_tuple:
            raise ValueError("At least one scenario validator is required")
        self._roles_catalog_generator = RolesCatalogGenerator(
            designer=designer,
            validators=catalog_validator_tuple,
            max_attempts=max_attempts,
        )
        self._interaction_generator = InteractionScenarioGenerator(
            designer=designer,
            validators=scenario_validator_tuple,
            max_attempts=max_attempts,
        )
        self._max_parallel_workers = max_parallel_workers
        self.logger: logging.Logger = logging.getLogger(self.__class__.__name__)

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

        roles_attempts, catalog = self._roles_catalog_generator.generate(scenario)
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
            attempts, interaction = self._interaction_generator.generate(
                req, catalog, graph
            )
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
        return self._interaction_generator.generate(req, catalog, graph)
