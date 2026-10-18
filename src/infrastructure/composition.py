"""Single composition root for the application.

Every service is wired here explicitly; there is no DI container. This
module is expected to change when a new component (a stage, a renderer,
a validator) is added: that is the point of a composition root. The
diagram renderer itself is diagram-type agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass

from application.pipeline.diagram_subjects import SequenceDiagramSubject
from application.pipeline.ports import (
    ArtifactWriter,
    DiagramRenderer,
    GenerationReporter,
)
from application.pipeline.runner import PipelineRunner
from application.pipeline.stage import PipelineStage
from application.pipeline.stages.api import ApiStage
from application.pipeline.stages.c4 import C4Stage
from application.pipeline.stages.sequence import SequenceStage
from application.services.api_generation_service import ApiGenerationService
from application.services.design_generation_service import DesignGenerationService
from application.services.sequence_generation_service import SequenceGenerationService
from config.root import AppSettings, load_app_settings
from domain.models.topology import ArchitectureGraph
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
from infrastructure.visualisation.plantuml.c4_container_builder import (
    C4ContainerDiagramBuilder,
)
from infrastructure.visualisation.plantuml.diagram_service import DiagramSourceBuilder
from infrastructure.visualisation.plantuml.renderers import PlantUmlDiagramRenderer
from infrastructure.visualisation.plantuml.sequence_builder import (
    SequenceDiagramBuilder,
)


def build_design_generation_service(
    settings: AppSettings | None = None,
) -> DesignGenerationService:
    """Wires config -> LiteLlmClient -> ArchitectureDesignerAgent -> service."""
    resolved: AppSettings = settings or load_app_settings()
    client: LiteLlmClient = LiteLlmClient(settings=resolved)
    designer: ArchitectureDesignerAgent = ArchitectureDesignerAgent(
        client=client, settings=resolved
    )
    validators: list[BaseValidator] = [StructuralTopologyValidator()]
    scenario_validators: list[ScenarioValidator] = [
        RequirementValidationDispatcher([BudgetRequirementValidator()])
    ]
    return DesignGenerationService(
        designer=designer,
        validators=validators,
        max_attempts=resolved.generation.max_attempts,
        scenario_validators=scenario_validators,
    )


def build_sequence_generation_service(
    settings: AppSettings | None = None,
) -> SequenceGenerationService:
    """Wires config -> LiteLlmClient -> SequenceDesignerAgent -> service."""
    resolved: AppSettings = settings or load_app_settings()
    client: LiteLlmClient = LiteLlmClient(settings=resolved)
    designer: SequenceDesignerAgent = SequenceDesignerAgent(
        client=client, settings=resolved
    )
    return SequenceGenerationService(
        designer=designer,
        validator=SequenceValidator(),
        max_attempts=resolved.generation.max_attempts,
    )


def build_api_generation_service(
    settings: AppSettings | None = None,
) -> ApiGenerationService:
    """Wires config -> LiteLlmClient -> ApiDesignerAgent -> ApiGenerationService."""
    resolved: AppSettings = settings or load_app_settings()
    client: LiteLlmClient = LiteLlmClient(settings=resolved)
    designer: ApiDesignerAgent = ApiDesignerAgent(client=client, settings=resolved)
    return ApiGenerationService(
        designer=designer,
        validator=ApiDesignValidator(),
        max_attempts=resolved.generation.max_attempts,
    )


def _diagram_renderer(
    source_builder: DiagramSourceBuilder,
    *,
    server: str,
    image_format: DiagramImageFormat,
    enabled: bool,
) -> PlantUmlDiagramRenderer[object] | None:
    """Builds a PlantUML renderer for any diagram type, or None when disabled."""
    if not enabled:
        return None
    return PlantUmlDiagramRenderer(
        source_builder=source_builder,
        server=server,
        image_format=image_format,
    )


def _build_c4_stage(
    settings: AppSettings,
    *,
    renderer: DiagramRenderer[ArchitectureGraph] | None,
    reporter: GenerationReporter,
) -> C4Stage:
    return C4Stage(
        service=build_design_generation_service(settings),
        renderer=renderer,
        reporter=reporter,
    )


def _build_sequence_stage(
    settings: AppSettings,
    *,
    renderer: DiagramRenderer[SequenceDiagramSubject] | None,
    reporter: GenerationReporter,
) -> SequenceStage:
    return SequenceStage(
        service=build_sequence_generation_service(settings),
        renderer=renderer,
        reporter=reporter,
    )


def _build_api_stage(
    settings: AppSettings,
    *,
    reporter: GenerationReporter,
) -> ApiStage:
    return ApiStage(
        service=build_api_generation_service(settings),
        renderer=DefaultApiArtifactRenderer(),
        reporter=reporter,
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
    settings: AppSettings = load_app_settings()
    c4_renderer = _diagram_renderer(
        C4ContainerDiagramBuilder(),
        server=diagram_server,
        image_format=image_format,
        enabled=render_diagrams,
    )
    sequence_renderer = _diagram_renderer(
        SequenceDiagramBuilder(),
        server=diagram_server,
        image_format=image_format,
        enabled=render_diagrams,
    )
    generation_reporter = LoggingGenerationReporter()

    stages: list[PipelineStage] = [
        _build_c4_stage(settings, renderer=c4_renderer, reporter=generation_reporter),
        _build_sequence_stage(
            settings, renderer=sequence_renderer, reporter=generation_reporter
        ),
        _build_api_stage(settings, reporter=generation_reporter),
    ]

    return PipelineWiring(
        runner=PipelineRunner(
            stages=stages,
            reporter=LoggingPipelineReporter(),
        ),
        writer=FileSystemArtifactWriter(),
    )
