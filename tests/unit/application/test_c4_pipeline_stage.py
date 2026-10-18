"""Unit tests for architecture generation and C4 stage outcomes."""

from collections.abc import Sequence
from pathlib import Path

import pytest

from application.pipeline.context import StageContext
from application.pipeline.outcome import DiagramRenderResult, StageOutcome, StageStatus
from application.pipeline.stages.c4 import C4Stage
from application.results import DesignGenerationResult, GenerationAttempt
from application.usage import TokenUsage
from domain.models.scenarios import DesignScenario
from domain.models.topology import ArchitectureGraph
from domain.specifications.interfaces import ValidationResult

pytestmark = pytest.mark.unit


class InMemoryWriter:
    def __init__(self) -> None:
        self.writes: list[tuple[Path, str]] = []

    def write_text(self, path: Path, content: str) -> Path:
        self.writes.append((path, content))
        return path


class NullReporter:
    def __init__(self) -> None:
        self.labels: list[str] = []

    def attempts(self, attempts: Sequence[GenerationAttempt], label: str) -> None:
        self.labels.append(label)

    def tokens(self, usage: TokenUsage, generation_seconds: float) -> None:
        assert usage.total_tokens >= 0
        assert generation_seconds >= 0.0


class FakeDesignGenerator:
    def __init__(self, result: DesignGenerationResult) -> None:
        self.result = result
        self.calls = 0

    def generate(self, scenario: DesignScenario) -> DesignGenerationResult:
        del scenario
        self.calls += 1
        return self.result


class FakeC4Renderer:
    def __init__(self, result: DiagramRenderResult) -> None:
        self.result = result
        self.calls = 0

    def render(
        self,
        subject: ArchitectureGraph,
        *,
        title: str,
        base_name: str,
        out_dir: Path,
    ) -> DiagramRenderResult:
        assert isinstance(subject, ArchitectureGraph)
        assert "C4 Container: c4_stage_test" in title
        assert base_name == "c4_stage_test_c4"
        assert out_dir.name == "output"
        self.calls += 1
        return self.result


def _scenario() -> DesignScenario:
    return DesignScenario(
        identifier="c4_stage_test",
        description="C4 stage test",
    )


def _graph() -> ArchitectureGraph:
    return ArchitectureGraph(nodes=[], edges=[])


def _success_result() -> DesignGenerationResult:
    graph = _graph()
    return DesignGenerationResult(
        attempts=[
            GenerationAttempt[ArchitectureGraph](
                attempt_number=1,
                parsed=True,
                payload=graph,
                validation=ValidationResult(),
                usage=TokenUsage(prompt_tokens=10, completion_tokens=20),
            )
        ]
    )


def _failed_result() -> DesignGenerationResult:
    return DesignGenerationResult(
        attempts=[
            GenerationAttempt[ArchitectureGraph](
                attempt_number=1,
                parsed=True,
                payload=_graph(),
                validation=ValidationResult(
                    errors=[
                        # A generic domain error is enough to characterize the
                        # stage's failure behavior; detailed validator contracts
                        # are covered by validator unit tests.
                        __import__(
                            "domain.exceptions.architecture_errors",
                            fromlist=["ArchitectureValidationError"],
                        ).ArchitectureValidationError("invalid topology")
                    ]
                ),
                usage=TokenUsage(prompt_tokens=10, completion_tokens=20),
            )
        ]
    )


def _context(tmp_path: Path, writer: InMemoryWriter) -> StageContext:
    return StageContext(
        scenario=_scenario(),
        out_dir=tmp_path / "output",
        writer=writer,
        upstream={},
    )


def test_c4_stage_persists_graph_and_renders_diagram(tmp_path: Path) -> None:
    writer = InMemoryWriter()
    generator = FakeDesignGenerator(_success_result())
    renderer = FakeC4Renderer(
        DiagramRenderResult(artifacts=(tmp_path / "output" / "c4.svg",))
    )
    reporter = NullReporter()
    stage = C4Stage(generator, renderer, reporter)

    outcome = stage.run(_context(tmp_path, writer))

    assert outcome.status is StageStatus.SUCCEEDED
    assert outcome.payload == _graph()
    assert generator.calls == 1
    assert renderer.calls == 1
    assert reporter.labels == ["C4 generation attempts"]
    assert [path.name for path, _ in writer.writes] == ["c4_stage_test_c4.json"]
    assert [path.name for path in outcome.artifacts] == [
        "c4_stage_test_c4.json",
        "c4.svg",
    ]


def test_c4_stage_marks_renderer_warnings_as_partial(tmp_path: Path) -> None:
    writer = InMemoryWriter()
    generator = FakeDesignGenerator(_success_result())
    renderer = FakeC4Renderer(
        DiagramRenderResult(warnings=("renderer unavailable",))
    )
    stage = C4Stage(generator, renderer, NullReporter())

    outcome = stage.run(_context(tmp_path, writer))

    assert outcome.status is StageStatus.PARTIAL
    assert outcome.warnings == ("renderer unavailable",)
    assert outcome.payload is not None
    assert len(writer.writes) == 1


def test_c4_stage_persists_diagnostic_graph_but_fails_invalid_design(
    tmp_path: Path,
) -> None:
    writer = InMemoryWriter()
    generator = FakeDesignGenerator(_failed_result())
    renderer = FakeC4Renderer(DiagramRenderResult())
    stage = C4Stage(generator, renderer, NullReporter())

    outcome = stage.run(_context(tmp_path, writer))

    assert outcome.status is StageStatus.FAILED
    assert outcome.payload is None
    assert renderer.calls == 0
    assert [path.name for path, _ in writer.writes] == ["c4_stage_test_c4.json"]
