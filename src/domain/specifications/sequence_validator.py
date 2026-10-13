from domain.exceptions.architecture_errors import ArchitectureValidationError
from domain.models.roles import ProjectRolesCatalog
from domain.models.sequence import ComponentLifeline, InteractionScenario, UserLifeline
from domain.models.topology import ArchitectureGraph
from domain.specifications.interfaces import ValidationResult


class SequenceIntegrityError(ArchitectureValidationError):
    """Raised when sequence diagram AST breaks referential integrity."""

    error_code: str = "SEQUENCE_INTEGRITY_ERROR"


class SequenceValidator:
    """Validates the logic and referential integrity of generated interaction scenarios."""

    def validate_catalog(self, catalog: ProjectRolesCatalog) -> ValidationResult:
        """Ensures the roles catalog is internally consistent."""
        errors: list[ArchitectureValidationError] = []
        seen_roles: set[str] = set()
        for role in catalog.roles:
            if role.role_id in seen_roles:
                errors.append(
                    SequenceIntegrityError(f"Duplicate role_id: {role.role_id}")
                )
            seen_roles.add(role.role_id)
        return ValidationResult(errors=errors)

    def validate_scenario(
        self,
        scenario: InteractionScenario,
        catalog: ProjectRolesCatalog,
        graph: ArchitectureGraph,
        expected_requirement_id: str,
    ) -> ValidationResult:
        """Ensures the AST correctly references the C4 graph and the roles catalog."""
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
            if isinstance(lifeline, UserLifeline):
                if lifeline.business_role_id not in valid_role_ids:
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
