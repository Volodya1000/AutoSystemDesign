"""Referential-integrity rules for sequence diagrams."""

from __future__ import annotations

from domain.exceptions.sequence_errors import SequenceIntegrityError
from domain.models.sequence import ComponentLifeline, InteractionScenario, UserLifeline
from domain.specifications.interfaces import ValidationResult

from .protocols import SequenceCatalogValidator, SequenceScenarioValidator


class SequenceIntegrityValidator(SequenceCatalogValidator, SequenceScenarioValidator):
    """Validate references between the roles catalog, architecture and scenario."""

    def validate_catalog(self, catalog: ProjectRolesCatalog) -> ValidationResult:
        errors: list[ArchitectureValidationError] = []
        seen_roles: set[str] = set()
        for role in catalog.roles:
            if role.role_id in seen_roles:
                errors.append(SequenceIntegrityError(f"Duplicate role_id: {role.role_id}"))
            seen_roles.add(role.role_id)
        return ValidationResult(errors=errors)

    def validate_scenario(
        self,
        scenario: InteractionScenario,
        catalog: ProjectRolesCatalog,
        graph: ArchitectureGraph,
        expected_requirement_id: str,
    ) -> ValidationResult:
        errors: list[ArchitectureValidationError] = []
        if scenario.requirement_identifier != expected_requirement_id:
            errors.append(
                SequenceIntegrityError(
                    f"Scenario claims to implement '{scenario.requirement_identifier}', "
                    f"but was requested for '{expected_requirement_id}'."
                )
            )

        valid_role_ids = {role.role_id for role in catalog.roles}
        valid_node_ids = {node.identifier for node in graph.nodes}
        for lifeline in scenario.lifelines:
            if isinstance(lifeline, UserLifeline) and lifeline.business_role_id not in valid_role_ids:
                errors.append(
                    SequenceIntegrityError(
                        f"UserLifeline '{lifeline.lifeline_id}' references unknown "
                        f"business_role_id '{lifeline.business_role_id}'."
                    )
                )
            elif (
                isinstance(lifeline, ComponentLifeline)
                and lifeline.architecture_node_id not in valid_node_ids
            ):
                errors.append(
                    SequenceIntegrityError(
                        f"ComponentLifeline '{lifeline.lifeline_id}' references unknown "
                        f"architecture_node_id '{lifeline.architecture_node_id}'. "
                        "Must be a valid C4 node."
                    )
                )
        return ValidationResult(errors=errors)


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.exceptions.architecture_errors import ArchitectureValidationError
    from domain.models.roles import ProjectRolesCatalog
    from domain.models.topology import ArchitectureGraph
