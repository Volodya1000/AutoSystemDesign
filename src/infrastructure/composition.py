"""Single composition root for the application.

Every service is wired here explicitly; there is no DI container. This
module is expected to change when a new component (a stage, a renderer,
a validator) is added: that is the point of a composition root. The
diagram renderer itself is diagram-type agnostic, so adding a new kind
of diagram to an existing stage does not touch this file either.
"""

from __future__ import annotations

from dataclasses import dataclass

from application.pipeline.ports import ArtifactWriter
from application.pipeline.runner import PipelineRunner
from application.pipeline.stage import PipelineStage
from application.pipeline.stages.api import ApiStage
from application.pipeline.stages.c4 import C4Stage
from application.pipeline.stages.sequence import SequenceStage
from application.services.api_generation_service import ApiGenerationService
from application.services.design_generation_service import DesignGenerationService
from application.services.sequence_generation_service import SequenceGenerationService
from config.root import AppSettings, load_app_settings
from domain.specifications.api_validator import ApiDesignValidator
from domain.specifications.budget_validator import BudgetRequirementValidator
from domain.specifications.interfaces import BaseValidator, ScenarioValidator
from domain.specifications.requirement_dispatch import RequirementValidationDispatcher
from domain.specifications.sequence_validator import SequenceValidator
from domain.specifications.structural_validator import StructuralTopologyValidator
from infrastructure.agents.api_designer import ApiDesignerAgent
from infrastructure.agents.designer import ArchitectureDesignerAgent
from infrastructure.agents.sequence_designer import SequenceDesignerAgent
from infrastructure.llm.client import LiteLlmClient
from infrastructure.persistence.artifact_writer import FileSystemArtifactWriter
from infrastructure.reporting import (
    LoggingGenerationReporter,
    LoggingPipelineReporter,
)
from infrastructure.visualisation.openapi.renderers import DefaultApiArtifactRenderer
from infrastructure.visualisation.plantuml import DiagramImageFormat
from infrastructure.visualisation.plantuml.renderers import make_plantuml_renderer


def build_design_generation_service() -> DesignGenerationService:
    """Wires config -> LiteLlmClient -> ArchitectureDesignerAgent -> service."""
    settings: AppSettings = load_app_settings()
    client: LiteLlmClient = LiteLlmClient(settings=settings)
    designer: ArchitectureDesignerAgent = ArchitectureDesignerAgent(
        client=client, settings=settings
    )
    validators: list[BaseValidator] = [StructuralTopologyValidator()]
    scenario_validators: list[ScenarioValidator] = [
        RequirementValidationDispatcher([BudgetRequirementValidator()])
    ]
    return DesignGenerationService(
        designer=designer,
        validators=validators,
        max_attempts=settings.generation.max_attempts,
        scenario_validators=scenario_validators,
    )


def build_sequence_generation_service() -> SequenceGenerationService:
    """Wires config -> LiteLlmClient -> SequenceDesignerAgent -> service."""
    settings: AppSettings = load_app_settings()
    client: LiteLlmClient = LiteLlmClient(settings=settings)
    designer: SequenceDesignerAgent = SequenceDesignerAgent(
        client=client, settings=settings
    )
    return SequenceGenerationService(
        designer=designer,
        validator=SequenceValidator(),
        max_attempts=settings.generation.max_attempts,
    )


def build_api_generation_service() -> ApiGenerationService:
    """Wires config -> LiteLlmClient -> ApiDesignerAgent -> ApiGenerationService."""
    settings: AppSettings = load_app_settings()
    client: LiteLlmClient = LiteLlmClient(settings=settings)
    designer: ApiDesignerAgent = ApiDesignerAgent(client=client, settings=settings)
    return ApiGenerationService(
        designer=designer,
        validator=ApiDesignValidator(),
        max_attempts=settings.generation.max_attempts,
    )


@dataclass(frozen=True)
class PipelineWiring:
    runner: PipelineRunner
    writer: ArtifactWriter


def build_pipeline(
    *,
    diagram_server: str,
    image_format: DiagramImageFormat,
    render_diagrams: bool,
) -> PipelineWiring:
    """Builds the full C4 + Sequence + REST API design pipeline."""
    c4_renderer = (
        make_plantuml_renderer("c4", server=diagram_server, image_format=image_format)
        if render_diagrams
        else None
    )
    sequence_renderer = (
        make_plantuml_renderer(
            "sequence", server=diagram_server, image_format=image_format
        )
        if render_diagrams
        else None
    )
    generation_reporter = LoggingGenerationReporter()

    stages: list[PipelineStage] = [
        C4Stage(
            service=build_design_generation_service(),
            renderer=c4_renderer,
            reporter=generation_reporter,
        ),
        SequenceStage(
            service=build_sequence_generation_service(),
            renderer=sequence_renderer,
            reporter=generation_reporter,
        ),
        ApiStage(
            service=build_api_generation_service(),
            renderer=DefaultApiArtifactRenderer(),
            reporter=generation_reporter,
        ),
    ]

    return PipelineWiring(
        runner=PipelineRunner(
            stages=stages,
            reporter=LoggingPipelineReporter(),
        ),
        writer=FileSystemArtifactWriter(),
    )
