from application.services.design_generation_service import DesignGenerationService
from application.services.sequence_generation_service import SequenceGenerationService
from config.root import AppSettings, load_app_settings
from domain.specifications.budget_validator import BudgetRequirementValidator
from domain.specifications.interfaces import BaseValidator, ScenarioValidator
from domain.specifications.requirement_dispatch import (
    RequirementValidationDispatcher,
)
from domain.specifications.sequence_validator import SequenceValidator
from domain.specifications.structural_validator import StructuralTopologyValidator
from infrastructure.agents.designer import ArchitectureDesignerAgent
from infrastructure.agents.sequence_designer import SequenceDesignerAgent
from infrastructure.llm.client import LiteLlmClient


def build_design_generation_service() -> DesignGenerationService:
    """Wires config -> LiteLlmClient -> ArchitectureDesignerAgent -> service."""
    settings: AppSettings = load_app_settings()
    client: LiteLlmClient = LiteLlmClient(settings=settings)
    designer: ArchitectureDesignerAgent = ArchitectureDesignerAgent(
        client=client, settings=settings
    )
    validators: list[BaseValidator] = [StructuralTopologyValidator()]
    scenario_validators: list[ScenarioValidator] = [
        RequirementValidationDispatcher(
            [
                BudgetRequirementValidator(),
            ]
        )
    ]
    return DesignGenerationService(
        designer=designer,
        validators=validators,
        max_attempts=settings.generation.max_attempts,
        scenario_validators=scenario_validators,
    )


def build_sequence_generation_service() -> SequenceGenerationService:
    """Wires config -> LiteLlmClient -> SequenceDesignerAgent -> SequenceGenerationService."""
    settings = load_app_settings()
    client = LiteLlmClient(settings=settings)
    designer = SequenceDesignerAgent(client=client, settings=settings)
    validator = SequenceValidator()

    return SequenceGenerationService(
        designer=designer,
        validator=validator,
        max_attempts=settings.generation.max_attempts,
    )
