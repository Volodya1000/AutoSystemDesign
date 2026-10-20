"""Unit tests of the stage builders in the composition root.

These exercise the wiring without any LLM: ``_build_*_stage`` accepts an
explicit ``AppSettings``, so no environment variables or real endpoint
are required.
"""

import pytest
from pydantic import SecretStr

from application.pipeline.stage import StageId
from application.pipeline.stages.api import ApiStage
from application.pipeline.stages.c4 import C4Stage
from application.pipeline.stages.performance_analysis import PerformanceAnalysisStage
from application.pipeline.stages.sequence import SequenceStage
from application.results import GenerationStatus
from application.tasks import DesignProposal, DesignTask
from application.usage import TokenUsage
from config.llm import LlmSettings, StructuredOutputMode
from config.root import AppSettings
from domain.models import DesignScenario, LatencyRequirement, WorkloadProfile
from domain.models.enums import NodeType
from domain.models.topology import ArchitectureGraph
from infrastructure.composition import (
    _build_api_stage,
    _build_c4_stage,
    _build_performance_analysis_stage,
    _build_sequence_stage,
    build_design_generation_service,
    build_pipeline,
)
from infrastructure.reporting import LoggingGenerationReporter
from infrastructure.visualisation.plantuml import DiagramImageFormat
from tests.factories import create_test_compute_node, create_test_edge, create_test_node

pytestmark = pytest.mark.unit


def _settings() -> AppSettings:
    return AppSettings(
        base_url="http://localhost:1234/v1",
        api_key=SecretStr("fake"),
        llm=LlmSettings(
            model="lm_studio/fake",
            temperature=0.0,
            max_tokens=64,
            timeout_seconds=5.0,
            structured_output_mode=StructuredOutputMode.PROMPT,
        ),
    )


def test_build_c4_stage_without_renderer() -> None:
    stage = _build_c4_stage(
        _settings(), renderer=None, reporter=LoggingGenerationReporter()
    )
    assert isinstance(stage, C4Stage)
    assert stage.name is StageId.C4
    assert not stage.depends_on


def test_build_performance_analysis_stage_depends_on_c4() -> None:
    stage = _build_performance_analysis_stage()
    assert isinstance(stage, PerformanceAnalysisStage)
    assert stage.name is StageId.PERFORMANCE_ANALYSIS
    assert stage.depends_on == (StageId.C4,)


def test_build_sequence_stage_depends_on_c4() -> None:
    stage = _build_sequence_stage(
        _settings(), renderer=None, reporter=LoggingGenerationReporter()
    )
    assert isinstance(stage, SequenceStage)
    assert stage.name is StageId.SEQUENCE
    assert stage.depends_on == (StageId.C4,)


def test_build_api_stage_depends_on_c4_and_sequence() -> None:
    stage = _build_api_stage(_settings(), reporter=LoggingGenerationReporter())
    assert isinstance(stage, ApiStage)
    assert stage.name is StageId.API
    assert stage.depends_on == (StageId.C4, StageId.SEQUENCE)


def test_build_pipeline_reuses_provided_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_reloaded() -> AppSettings:
        pytest.fail("build_pipeline reloaded application settings")

    monkeypatch.setattr(
        "infrastructure.composition.load_app_settings", fail_if_reloaded
    )

    wiring = build_pipeline(
        settings=_settings(),
        diagram_server="kroki",
        image_format=DiagramImageFormat.PNG,
        render_diagrams=False,
    )

    assert wiring.runner is not None
    assert wiring.writer is not None



class _FakeLlmClient:
    def __init__(self, settings: AppSettings) -> None:
        del settings


class _FixedArchitectureDesigner:
    def __init__(self, proposal: DesignProposal) -> None:
        self._proposal = proposal
        self.received_tasks: list[DesignTask] = []

    def propose(self, task: DesignTask) -> DesignProposal:
        self.received_tasks.append(task)
        return self._proposal


def test_unmodelled_percentile_target_does_not_trigger_repair_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node(
                "service",
                concurrency=1,
                mean_ms=10.0,
                std_ms=10.0,
            ),
        ],
        edges=[create_test_edge("client", "service")],
    )
    scenario = DesignScenario(
        identifier="latency_slo_test",
        description="A percentile target that the current model cannot evaluate",
        workload=WorkloadProfile(
            baseline_requests_per_second=10.0,
            peak_requests_per_second=20.0,
        ),
        requirements=[LatencyRequirement(threshold_value=1.0, percentile=99.0)],
    )
    designer = _FixedArchitectureDesigner(
        DesignProposal(graph=graph, raw_content="{}", usage=TokenUsage())
    )

    def build_fixed_designer(
        client: _FakeLlmClient,
        settings: AppSettings,
    ) -> _FixedArchitectureDesigner:
        del client, settings
        return designer

    monkeypatch.setattr("infrastructure.composition.LiteLlmClient", _FakeLlmClient)
    monkeypatch.setattr(
        "infrastructure.composition.ArchitectureDesignerAgent",
        build_fixed_designer,
    )

    service = build_design_generation_service(settings=_settings())
    result = service.generate(scenario)

    assert result.status is GenerationStatus.SUCCEEDED
    assert len(result.attempts) == 1
    assert len(designer.received_tasks) == 1
