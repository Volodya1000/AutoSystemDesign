"""Composition root: manual DI wiring of the full generation pipeline."""

from application.services.design_generation_service import DesignGenerationService
from config.root import AppSettings, load_app_settings
from domain.specifications.interfaces import BaseValidator
from domain.specifications.structural_validator import StructuralTopologyValidator
from infrastructure.agents.designer import ArchitectureDesignerAgent
from infrastructure.llm.client import LiteLlmClient


def build_design_generation_service() -> DesignGenerationService:
    """Wires config -> LiteLlmClient -> ArchitectureDesignerAgent -> service."""
    settings: AppSettings = load_app_settings()
    client: LiteLlmClient = LiteLlmClient(settings=settings)
    designer: ArchitectureDesignerAgent = ArchitectureDesignerAgent(
        client=client, settings=settings
    )
    validators: list[BaseValidator] = [StructuralTopologyValidator()]
    return DesignGenerationService(
        designer=designer,
        validators=validators,
        max_attempts=settings.generation.max_attempts,
    )
