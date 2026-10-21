"""Contract tests for the pipeline architecture."""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Never, TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from application.pipeline.context import (
    PipelineDependencyError,
    StageContext,
    require_payload,
)
from application.pipeline.outcome import DiagramRenderResult, StageOutcome, StageStatus
from application.pipeline.runner import PipelineRunner
from application.pipeline.stages._naming import plan_base_names
from domain.models.topology import ArchitectureGraph
from infrastructure.visualisation.plantuml import (
    DiagramArtifacts,
    DiagramImageFormat,
    DiagramRenderingError,
    DiagramSavingError,
)
from infrastructure.visualisation.plantuml import renderers as renderers_mod
from tests.unit.in_memory_writer import InMemoryWriter

if TYPE_CHECKING:
    from collections.abc import Sequence

    from application.results import GenerationAttempt
    from application.usage import TokenUsage


class ProgrammingError(ValueError):
    """Unexpected programming error used to test propagation."""

    def __init__(self) -> None:
        super().__init__("programming error")


class NullGenerationReporter:
    def attempts[PayloadT](
        self, attempts: Sequence[GenerationAttempt[PayloadT]], label: str
    ) -> None: ...

    def tokens(self, usage: TokenUsage, generation_seconds: float) -> None: ...


class CapturingPipelineReporter:
    def __init__(self) -> None:
        self.reports: list[list[StageOutcome[object]]] = []

    def report(self, outcomes: Sequence[StageOutcome[object]]) -> None:
        self.reports.append(list(outcomes))


class FakeStage:
    def __init__(
        self,
        name: str,
        depends_on: tuple[str, ...] = (),
        status: StageStatus = StageStatus.SUCCEEDED,
        payload: object | None = None,
    ) -> None:
        self.name: str = name
        self.depends_on: tuple[str, ...] = depends_on
        self.status: StageStatus = status
        self.payload: object | None = payload
        self.calls: list[StageContext] = []

    def run(self, context: StageContext) -> StageOutcome[object]:
        self.calls.append(context)
        return StageOutcome(
            name=self.name,
            status=self.status,
            duration_seconds=0,
            total_tokens=0,
            payload=self.payload,
        )


def _scenario() -> MagicMock:
    return MagicMock(name="DesignScenario")


def _context(
    tmp_path: Path,
    upstream: dict[str, StageOutcome[object]],
) -> StageContext:
    return StageContext(
        scenario=_scenario(),
        out_dir=tmp_path,
        writer=InMemoryWriter(),
        upstream=MappingProxyType(upstream),
    )


def _outcome(
    name: str,
    status: StageStatus,
    payload: object | None = None,
) -> StageOutcome[object]:
    return StageOutcome(
        name=name,
        status=status,
        duration_seconds=0,
        total_tokens=0,
        payload=payload,
    )


# --- runner validation ------------------------------------------------------


def test_runner_rejects_empty_pipeline() -> None:
    with pytest.raises(ValueError, match="at least one stage"):
        PipelineRunner(stages=[], reporter=CapturingPipelineReporter())


def test_runner_rejects_duplicate_stage_names() -> None:
    with pytest.raises(ValueError, match="Duplicate stage name 'c4'"):
        PipelineRunner(
            stages=[FakeStage(name="c4"), FakeStage(name="c4")],
            reporter=CapturingPipelineReporter(),
        )


def test_runner_rejects_missing_dependency() -> None:
    with pytest.raises(ValueError, match="depends on 'c4'"):
        PipelineRunner(
            stages=[FakeStage(name="sequence", depends_on=("c4",))],
            reporter=CapturingPipelineReporter(),
        )


def test_runner_rejects_out_of_order_dependency() -> None:
    with pytest.raises(ValueError, match="depends on 'c4'"):
        PipelineRunner(
            stages=[
                FakeStage(name="sequence", depends_on=("c4",)),
                FakeStage(name="c4"),
            ],
            reporter=CapturingPipelineReporter(),
        )


# --- runner execution -------------------------------------------------------


def test_runner_succeeds_on_all_succeeded(tmp_path: Path) -> None:
    runner = PipelineRunner(
        stages=[FakeStage(name="c4")],
        reporter=CapturingPipelineReporter(),
    )
    assert runner.run(_scenario(), tmp_path, InMemoryWriter()) == 0


def test_runner_returns_1_on_stage_failed(tmp_path: Path) -> None:
    reporter = CapturingPipelineReporter()
    runner = PipelineRunner(
        stages=[FakeStage(name="c4", status=StageStatus.FAILED)],
        reporter=reporter,
    )
    assert runner.run(_scenario(), tmp_path, InMemoryWriter()) == 1
    assert reporter.reports[-1][0].status is StageStatus.FAILED


def test_runner_partial_is_not_a_failure(tmp_path: Path) -> None:
    """PARTIAL means optional artifacts (diagrams) failed; exit code is 0."""
    reporter = CapturingPipelineReporter()
    runner = PipelineRunner(
        stages=[FakeStage(name="c4", status=StageStatus.PARTIAL)],
        reporter=reporter,
    )
    assert runner.run(_scenario(), tmp_path, InMemoryWriter()) == 0
    assert reporter.reports[-1][0].status is StageStatus.PARTIAL


def test_runner_stops_after_failed_stage(tmp_path: Path) -> None:
    second = FakeStage(name="sequence", depends_on=("c4",))
    runner = PipelineRunner(
        stages=[
            FakeStage(name="c4", status=StageStatus.FAILED),
            second,
        ],
        reporter=CapturingPipelineReporter(),
    )
    assert runner.run(_scenario(), tmp_path, InMemoryWriter()) == 1
    assert not second.calls  # never invoked


# --- require_payload --------------------------------------------------------


def test_require_payload_accepts_partial(tmp_path: Path) -> None:
    graph = MagicMock(spec=ArchitectureGraph)
    ctx = _context(
        tmp_path,
        {"c4": _outcome("c4", StageStatus.PARTIAL, payload=graph)},
    )
    assert require_payload(ctx, "c4", ArchitectureGraph) is graph


def test_require_payload_rejects_failed(tmp_path: Path) -> None:
    ctx = _context(tmp_path, {"c4": _outcome("c4", StageStatus.FAILED)})
    with pytest.raises(PipelineDependencyError, match="failed"):
        require_payload(ctx, "c4", ArchitectureGraph)


def test_require_payload_rejects_missing(tmp_path: Path) -> None:
    with pytest.raises(PipelineDependencyError, match="Missing upstream stage"):
        require_payload(_context(tmp_path, {}), "c4", ArchitectureGraph)


def test_require_payload_rejects_wrong_type(tmp_path: Path) -> None:
    ctx = _context(
        tmp_path,
        {"c4": _outcome("c4", StageStatus.SUCCEEDED, payload={"x": 1})},
    )
    with pytest.raises(PipelineDependencyError, match="expected ArchitectureGraph"):
        require_payload(ctx, "c4", ArchitectureGraph)


# --- render_and_write contract ---------------------------------------------


def test_render_and_write_captures_source_generation_error() -> None:
    """DiagramRenderingError during service.generate() becomes a warning."""
    service = MagicMock()
    service.generate.side_effect = DiagramRenderingError("server down")
    result = renderers_mod.render_and_write(
        service_factory=lambda: service,
        subject=MagicMock(),
        title="t",
        base_name="b",
        out_dir=Path("."),
    )
    assert result.warnings
    assert "server down" in result.warnings[0]
    assert not result.artifacts
    assert result.image_rendered is False


def test_render_and_write_image_failure_keeps_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """render_image() fails but the source is still written to disk."""
    service = MagicMock()
    service.generate.return_value = "artifacts"
    service.render_image.side_effect = DiagramRenderingError("no server")

    written_paths: list[Path] = [tmp_path / "b.puml"]
    fake_writer = MagicMock()
    fake_writer.write.return_value = written_paths
    monkeypatch.setattr(renderers_mod, "DiagramFileWriter", lambda: fake_writer)

    result = renderers_mod.render_and_write(
        service_factory=lambda: service,
        subject=MagicMock(),
        title="t",
        base_name="b",
        out_dir=tmp_path,
    )
    assert result.artifacts == tuple(written_paths)
    assert result.warnings
    assert "no server" in result.warnings[0]
    assert result.image_rendered is False


def test_render_and_write_saving_failure_returns_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """DiagramSavingError on write() becomes a warning, artifacts empty."""
    service = MagicMock()
    service.generate.return_value = DiagramArtifacts(
        source="@startuml\\n@enduml",
        image_url="https://example.invalid/diagram.svg",
        image_format=DiagramImageFormat.SVG,
    )
    service.render_image.return_value = b"img"

    fake_writer = MagicMock()
    fake_writer.write.side_effect = DiagramSavingError(tmp_path, OSError("disk full"))
    monkeypatch.setattr(renderers_mod, "DiagramFileWriter", lambda: fake_writer)

    result = renderers_mod.render_and_write(
        service_factory=lambda: service,
        subject=MagicMock(),
        title="t",
        base_name="b",
        out_dir=tmp_path,
    )
    assert not result.artifacts
    assert result.warnings
    assert "disk full" in result.warnings[0]
    assert result.image_rendered is True


def test_render_and_write_propagates_unexpected_error() -> None:
    """Programming errors (e.g. ValueError) are not swallowed."""

    def bad_factory() -> Never:
        raise ProgrammingError

    with pytest.raises(ValueError, match="programming error"):
        renderers_mod.render_and_write(
            service_factory=bad_factory,
            subject=MagicMock(),
            title="t",
            base_name="b",
            out_dir=Path("."),
        )


def test_render_and_write_propagates_unexpected_generate_error() -> None:
    service = MagicMock()
    service.generate.side_effect = RuntimeError("not a diagram error")
    with pytest.raises(RuntimeError, match="not a diagram error"):
        renderers_mod.render_and_write(
            service_factory=lambda: service,
            subject=MagicMock(),
            title="t",
            base_name="b",
            out_dir=Path("."),
        )


# --- requirement id collisions ----------------------------------------------


def test_requirement_id_collision_detected() -> None:
    with pytest.raises(ValueError, match="collision"):
        plan_base_names("scn", ["REQ-1", "REQ_1"])


def test_requirement_ids_do_not_collide() -> None:
    names = plan_base_names("scn", ["REQ-1", "REQ-2"])
    assert set(names.values()) == {"scn_seq_req_1", "scn_seq_req_2"}


# --- DiagramRenderResult sanity --------------------------------------------


def test_diagram_render_result_is_a_value_object() -> None:
    result = DiagramRenderResult(
        artifacts=(),
        warnings=("boom",),
        image_rendered=False,
    )
    assert result.warnings
    assert not result.artifacts
