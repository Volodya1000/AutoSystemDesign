from domain.exceptions.architecture_errors import ArchitectureValidationError
from domain.models.sequence import ComponentLifeline, UserLifeline
from domain.models.system_design import SystemDesignOutput
from domain.models.topology import ArchitectureGraph
from domain.specifications.interfaces import ValidationResult


class SequenceIntegrityError(ArchitectureValidationError):
    error_code: str = "SEQUENCE_INTEGRITY_ERROR"


class SequenceValidator:
    def validate(
        self, system_design: SystemDesignOutput, architecture_graph: ArchitectureGraph
    ) -> ValidationResult:
        errors = []

        valid_role_ids = {role.role_id for role in system_design.roles_catalog.roles}
        valid_node_ids = {node.identifier for node in architecture_graph.nodes}

        for scenario in system_design.interaction_scenarios:
            for lifeline in scenario.lifelines:
                if isinstance(lifeline, UserLifeline):
                    if lifeline.business_role_id not in valid_role_ids:
                        errors.append(
                            SequenceIntegrityError(
                                message=f"Lifeline '{lifeline.lifeline_id}' references unknown business_role_id '{lifeline.business_role_id}' in scenario '{scenario.scenario_id}'."
                            )
                        )
                elif isinstance(lifeline, ComponentLifeline):
                    if lifeline.architecture_node_id not in valid_node_ids:
                        errors.append(
                            SequenceIntegrityError(
                                message=f"Lifeline '{lifeline.lifeline_id}' references unknown architecture_node_id '{lifeline.architecture_node_id}' in scenario '{scenario.scenario_id}'. Must be one of the C4 nodes."
                            )
                        )

        return ValidationResult(errors=errors)
