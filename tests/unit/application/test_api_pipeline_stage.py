# Copyright (c) 2026 Volodya1000
"""Unit tests for persistence and status handling in the API pipeline stage."""

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from application.pipeline.context import StageContext
from application.pipeline.outcome import DiagramRenderResult, StageOutcome, StageStatus
from application.pipeline.stages.api import ApiStage
from application.results import ApiGenerationResult, GenerationAttempt
from application.usage import TokenUsage
from domain.models.api import ApiDesign, ApiOperation, ApiResponse, HttpMethod
from domain.models.functional import FunctionalRequirement
from domain.models.scenarios import DesignScenario
from domain.models.sequence import InteractionScenario
from domain.models.topology import ArchitectureGraph
from domain.specifications.interfaces import ValidationResult
from tests.unit.in_memory_writer import InMemoryWriter

pytestmark = pytest.mark.unit


class NullReporter:
    def __init__(self) -> None:
        self.labels: list[str] = []

    def attempts[PayloadT](
        self, attempts: Sequence[GenerationAttempt[PayloadT]], label: str
    ) -> None:
        self.labels.append(label)
        assert attempts

    def tokens(self, usage: TokenUsage, generation_seconds: float) -> None:
        assert usage.total_tokens >= 0
        assert generation_seconds >= 0.0


class FakeApiGenerator:
    def __init__(self, result: ApiGenerationResult) -> None:
        self.result = result
        self.calls = 0
        self.received_sequences: Mapping[str, InteractionScenario] | None = None

    def generate(
        self,
        scenario: DesignScenario,
        graph: ArchitectureGraph,
        sequences: Mapping[str, InteractionScenario],
    ) -> ApiGenerationResult:
        del scenario, graph
        self.calls += 1
        self.received_sequences = sequences
        return self.result


class FakeApiRenderer:
    def __init__(self, result: DiagramRenderResult) -> None:
        self.result = result
        self.calls = 0

    def render(
        self,
        subject: ApiDesign,
        *,
        title: str,
        base_name: str,
        out_dir: Path,
    ) -> DiagramRenderResult:
        assert subject.title == "Test API"
        assert title == "api_stage_test API"
        assert base_name == "api_stage_test_api"
        assert out_dir.name == "output"
        self.calls += 1
        return self.result


def _scenario() -> DesignScenario:
    return DesignScenario(
        identifier="api_stage_test",
        description="API stage test",
        functional_requirements=[
            FunctionalRequirement(
                identifier="FR-1",
                name="Create resource",
                text="A user creates a resource.",
            )
        ],
    )


def _design() -> ApiDesign:
    return ApiDesign(
        title="Test API",
        operations=[
            ApiOperation(
                operation_id="create_resource",
                method=HttpMethod.POST,
                path="/v1/resources",
                summary="Create a resource",
                entrypoint_component_id="api",
                handler_component_id="api",
                requirement_ids=["FR-1"],
                responses=[ApiResponse(status_code="201", description="Created")],
            )
        ],
    )


def _successful_result() -> ApiGenerationResult:
    design = _design()
    return ApiGenerationResult(
        attempts=[
            GenerationAttempt[ApiDesign](
                attempt_number=1,
                parsed=True,
                payload=design,
                validation=ValidationResult(),
                usage=TokenUsage(prompt_tokens=10, completion_tokens=20),
            )
        ],
        api_design=design,
    )


def _context(
    tmp_path: Path,
    writer: InMemoryWriter,
    scenario: DesignScenario | None = None,
) -> StageContext:
    return StageContext(
        scenario=scenario or _scenario(),
        out_dir=tmp_path / "output",
        writer=writer,
        upstream={
            "c4": StageOutcome[object](
                name="c4",
                status=StageStatus.SUCCEEDED,
                duration_seconds=0.0,
                total_tokens=0,
                payload=ArchitectureGraph(nodes=[], edges=[]),
            ),
            "sequence": StageOutcome[object](
                name="sequence",
                status=StageStatus.SUCCEEDED,
                duration_seconds=0.0,
                total_tokens=0,
                payload={},
            ),
        },
    )


def test_api_stage_persists_design_and_renderer_artifacts(tmp_path: Path) -> None:
    writer = InMemoryWriter()
    generator = FakeApiGenerator(_successful_result())
    renderer = FakeApiRenderer(
        DiagramRenderResult(artifacts=(tmp_path / "output" / "api.html",))
    )
    reporter = NullReporter()
    stage = ApiStage(generator, renderer, reporter)

    outcome = stage.run(_context(tmp_path, writer))

    assert outcome.status is StageStatus.SUCCEEDED
    assert outcome.payload is not None
    assert outcome.payload.title == "Test API"
    assert generator.calls == 1
    assert generator.received_sequences == {}
    assert renderer.calls == 1
    assert reporter.labels == ["API generation attempts"]
    assert [path.name for path, _ in writer.writes] == [
        "api_stage_test_api_design.json"
    ]
    assert [path.name for path in outcome.artifacts] == [
        "api_stage_test_api_design.json",
        "api.html",
    ]


def test_api_stage_marks_renderer_warnings_as_partial(tmp_path: Path) -> None:
    writer = InMemoryWriter()
    generator = FakeApiGenerator(_successful_result())
    renderer = FakeApiRenderer(
        DiagramRenderResult(warnings=("Swagger renderer unavailable",))
    )
    stage = ApiStage(generator, renderer, NullReporter())

    outcome = stage.run(_context(tmp_path, writer))

    assert outcome.status is StageStatus.PARTIAL
    assert outcome.warnings == ("Swagger renderer unavailable",)
    assert outcome.payload is not None
    assert len(writer.writes) == 1


def test_api_stage_fails_when_generation_has_no_valid_design(tmp_path: Path) -> None:
    failed_result = ApiGenerationResult(
        attempts=[
            GenerationAttempt[ApiDesign](
                attempt_number=1,
                parsed=False,
                usage=TokenUsage(prompt_tokens=5, completion_tokens=5),
            )
        ],
        api_design=None,
    )
    writer = InMemoryWriter()
    generator = FakeApiGenerator(failed_result)
    renderer = FakeApiRenderer(DiagramRenderResult())
    stage = ApiStage(generator, renderer, NullReporter())

    outcome = stage.run(_context(tmp_path, writer))

    assert outcome.status is StageStatus.FAILED
    assert outcome.payload is None
    assert renderer.calls == 0
    assert not writer.writes
