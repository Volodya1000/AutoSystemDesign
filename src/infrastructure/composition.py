"""Single composition root for the application.

Every service is wired here explicitly; there is no DI container. This
module is expected to change when a new component (a stage, a renderer,
a validator) is added: that is the point of a composition root. The
diagram renderer itself is diagram-type agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from application.pipeline.runner import PipelineRunner
from application.pipeline.stages.api import ApiStage
from application.pipeline.stages.c4 import C4Stage
from application.pipeline.stages.performance_analysis import PerformanceAnalysisStage
from application.pipeline.stages.sequence import SequenceStage
from application.services.api_generation_service import ApiGenerationService
from application.services.design_generation_service import DesignGenerationService
from application.services.sequence_generation_service import SequenceGenerationService
from config.root import AppSettings, load_app_settings
from domain.specifications.api_validator import ApiDesignValidator
from domain.specifications.broker_consumer_validator import (
    MessageBrokerConsumerValidator,
)
from domain.specifications.budget_validator import BudgetRequirementValidator
from domain.specifications.cache_usage_validator import CacheUsageValidator
from domain.specifications.capacity_validator import CapacitySaturationValidator
from domain.specifications.requirement_dispatch import RequirementValidationDispatcher
from domain.specifications.sequence_validation import (
    ClientOwnershipValidator,
    DeliveryModeValidator,
    SequenceIntegrityValidator,
    SequenceTopologyValidator,
)
from domain.specifications.structural_validator import StructuralTopologyValidator
from infrastructure.agents.api_designer import ApiDesignerAgent
from infrastructure.agents.designer import ArchitectureDesignerAgent
from infrastructure.agents.sequence_designer import SequenceDesignerAgent
from infrastructure.llm.client import LiteLlmClient
from infrastructure.performance_analysis.pdf_renderer import (
    PerformanceReportPdfRenderer,
)
from infrastructure.persistence.artifact_writer import FileSystemArtifactWriter
from infrastructure.reporting import LoggingGenerationReporter, LoggingPipelineReporter
from infrastructure.visualisation.openapi.renderers import DefaultApiArtifactRenderer
from infrastructure.visualisation.plantuml.c4_container_builder import (
    C4ContainerDiagramBuilder,
)
from infrastructure.visualisation.plantuml.element_specs import localized_element_specs
from infrastructure.visualisation.plantuml.renderers import PlantUmlDiagramRenderer
from infrastructure.visualisation.plantuml.sequence_builder import (
    SequenceDiagramBuilder,
)
from shared.artifact_language import ArtifactLanguage

if TYPE_CHECKING:
    from application.pipeline.diagram_subjects import SequenceDiagramSubject
    from application.pipeline.protocols import (
        ArtifactWriterProtocol,
        DiagramRendererProtocol,
        GenerationReporterProtocol,
    )
    from application.pipeline.stage import PipelineStageProtocol
    from domain.models.topology import ArchitectureGraph
    from domain.specifications.interfaces import BaseValidator, ScenarioValidator
    from infrastructure.visualisation.plantuml import DiagramImageFormat
    from infrastructure.visualisation.plantuml.protocols import (
        DiagramSourceBuilderProtocol,
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
    validators: list[BaseValidator] = [
        StructuralTopologyValidator(),
        MessageBrokerConsumerValidator(),
        CacheUsageValidator(),
    ]
    scenario_validators: list[ScenarioValidator] = [
        RequirementValidationDispatcher([BudgetRequirementValidator()]),
        CapacitySaturationValidator(),
    ]
    return DesignGenerationService(
        designer=designer,
        validators=validators,
        max_attempts=resolved.generation.max_attempts,
        scenario_validators=scenario_validators,
        service_profiles=resolved.service_profiles,
    )


def build_sequence_generation_service(
    settings: AppSettings | None = None,
) -> SequenceGenerationService:
    """Wires config -> LiteLlmClient -> SequenceDesignerAgent -> service.

    One ``SequenceIntegrityValidator`` instance serves both as a catalog
    validator and as a scenario validator: it is stateless, so sharing it
    keeps the wiring compact. The other two validators implement only
    the scenario rule.
    """
    resolved: AppSettings = settings or load_app_settings()
    client: LiteLlmClient = LiteLlmClient(settings=resolved)
    designer: SequenceDesignerAgent = SequenceDesignerAgent(
        client=client, settings=resolved
    )
    integrity = SequenceIntegrityValidator()
    return SequenceGenerationService(
        designer=designer,
        catalog_validators=[integrity],
        scenario_validators=[
            integrity,
            SequenceTopologyValidator(),
            ClientOwnershipValidator(),
            DeliveryModeValidator(),
        ],
        max_attempts=resolved.generation.max_attempts,
        max_parallel_workers=resolved.generation.sequence_parallelism,
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


def _diagram_renderer[SubjectT](
    source_builder: DiagramSourceBuilderProtocol[SubjectT],
    *,
    server: str,
    image_format: DiagramImageFormat,
    enabled: bool,
) -> PlantUmlDiagramRenderer[SubjectT] | None:
    """Build a renderer while preserving the source builder's subject type."""
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
    renderer: DiagramRendererProtocol[ArchitectureGraph] | None,
    reporter: GenerationReporterProtocol,
) -> C4Stage:
    return C4Stage(
        service=build_design_generation_service(settings),
        renderer=renderer,
        reporter=reporter,
        service_profiles=settings.service_profiles,
    )


def _build_performance_analysis_stage() -> PerformanceAnalysisStage:
    """Build the deterministic analysis stage without external dependencies."""
    return PerformanceAnalysisStage(pdf_renderer=PerformanceReportPdfRenderer())


def _build_sequence_stage(
    settings: AppSettings,
    *,
    renderer: DiagramRendererProtocol[SequenceDiagramSubject] | None,
    reporter: GenerationReporterProtocol,
) -> SequenceStage:
    return SequenceStage(
        service=build_sequence_generation_service(settings),
        renderer=renderer,
        reporter=reporter,
    )


def _build_api_stage(
    settings: AppSettings,
    *,
    reporter: GenerationReporterProtocol,
) -> ApiStage:
    return ApiStage(
        service=build_api_generation_service(settings),
        renderer=DefaultApiArtifactRenderer(),
        reporter=reporter,
    )


@dataclass(frozen=True)
class PipelineWiring:
    runner: PipelineRunner
    writer: ArtifactWriterProtocol


def build_pipeline(
    *,
    diagram_server: str,
    image_format: DiagramImageFormat,
    render_diagrams: bool,
    settings: AppSettings | None = None,
) -> PipelineWiring:
    """Build the C4 + performance analysis + Sequence + REST API pipeline."""
    resolved_settings: AppSettings = (
        settings if settings is not None else load_app_settings()
    )
    c4_builder: DiagramSourceBuilderProtocol[ArchitectureGraph] = (
        C4ContainerDiagramBuilder(
            element_specs=localized_element_specs(
                resolved_settings.generation.artifact_language
            ),
            system_boundary_label=(
                "Система"
                if resolved_settings.generation.artifact_language
                is ArtifactLanguage.RUSSIAN
                else "System"
            ),
        )
    )
    c4_renderer: PlantUmlDiagramRenderer[ArchitectureGraph] | None = _diagram_renderer(
        c4_builder,
        server=diagram_server,
        image_format=image_format,
        enabled=render_diagrams,
    )
    sequence_builder: DiagramSourceBuilderProtocol[SequenceDiagramSubject] = (
        SequenceDiagramBuilder()
    )
    sequence_renderer: PlantUmlDiagramRenderer[SequenceDiagramSubject] | None = (
        _diagram_renderer(
            sequence_builder,
            server=diagram_server,
            image_format=image_format,
            enabled=render_diagrams,
        )
    )
    generation_reporter = LoggingGenerationReporter()

    stages: list[PipelineStageProtocol] = [
        _build_c4_stage(
            resolved_settings, renderer=c4_renderer, reporter=generation_reporter
        ),
        _build_performance_analysis_stage(),
        _build_sequence_stage(
            resolved_settings, renderer=sequence_renderer, reporter=generation_reporter
        ),
        _build_api_stage(resolved_settings, reporter=generation_reporter),
    ]

    return PipelineWiring(
        runner=PipelineRunner(
            stages=stages,
            reporter=LoggingPipelineReporter(),
        ),
        writer=FileSystemArtifactWriter(),
    )
