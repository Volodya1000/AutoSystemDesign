"""Tests for persisting performance reports through the pipeline stage."""

from pathlib import Path

import pytest

from application.performance_analysis.protocols import PdfRenderingUnavailableError
from application.pipeline.context import StageContext
from application.pipeline.outcome import StageOutcome, StageStatus
from application.pipeline.stage import StageId
from application.pipeline.stages.performance_analysis import PerformanceAnalysisStage
from domain.models.enums import NodeType
from domain.models.scenarios import DesignScenario, WorkloadProfile
from domain.models.topology import ArchitectureGraph
from domain.performance_analysis.report import (
    PerformanceAnalysisReport,
    PerformanceAnalysisStatus,
)
from tests.factories import create_test_compute_node, create_test_edge, create_test_node
from tests.unit.in_memory_writer import InMemoryWriter

pytestmark = pytest.mark.unit


class _FakePdfRenderer:
    """Provide either rendered bytes or one expected optional failure."""

    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    def render(self, _report: PerformanceAnalysisReport) -> bytes:
        if self._fail:
            message = "Font is unavailable"
            raise PdfRenderingUnavailableError(message)
        return b"%PDF-1.4 test"


def _run_stage(
    out_dir: Path,
    workload: WorkloadProfile | None,
    pdf_renderer: _FakePdfRenderer | None = None,
) -> tuple[StageOutcome[PerformanceAnalysisReport], InMemoryWriter]:
    scenario = DesignScenario(
        identifier="store",
        description="Performance analysis stage test",
        workload=workload,
    )
    graph = ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node("service", service_channels_per_replica=1),
        ],
        edges=[create_test_edge("client", "service")],
    )
    writer = InMemoryWriter()
    upstream: dict[StageId, StageOutcome[object]] = {
        StageId.C4: StageOutcome[object](
            name=StageId.C4,
            status=StageStatus.PARTIAL,
            duration_seconds=0.0,
            total_tokens=0,
            payload=graph,
        )
    }
    context = StageContext(
        scenario=scenario,
        out_dir=out_dir,
        writer=writer,
        upstream=upstream,
    )

    outcome = PerformanceAnalysisStage(pdf_renderer=pdf_renderer).run(context)
    return outcome, writer


def test_stage_persists_report_from_c4_graph_and_workload(tmp_path: Path) -> None:
    outcome, writer = _run_stage(
        tmp_path,
        WorkloadProfile(
            baseline_requests_per_second=10.0,
            peak_requests_per_second=20.0,
        ),
    )

    assert outcome.status is StageStatus.SUCCEEDED
    assert outcome.payload is not None
    assert outcome.payload.status is PerformanceAnalysisStatus.PARTIAL
    assert outcome.artifacts == (tmp_path / "store_performance_analysis.json",)
    assert writer.writes[0][0] == outcome.artifacts[0]
    persisted_report = PerformanceAnalysisReport.model_validate_json(
        writer.writes[0][1]
    )
    assert persisted_report == outcome.payload


def test_missing_workload_is_a_valid_report_not_a_failed_stage(
    tmp_path: Path,
) -> None:
    outcome, writer = _run_stage(tmp_path, workload=None)

    assert outcome.status is StageStatus.SUCCEEDED
    assert outcome.payload is not None
    assert outcome.payload.status is PerformanceAnalysisStatus.UNAVAILABLE
    assert len(writer.writes) == 1
    assert outcome.artifacts == (writer.writes[0][0],)


def test_pdf_is_written_alongside_mandatory_json(tmp_path: Path) -> None:
    outcome, writer = _run_stage(
        tmp_path,
        workload=None,
        pdf_renderer=_FakePdfRenderer(),
    )

    assert outcome.status is StageStatus.SUCCEEDED
    assert len(outcome.artifacts) == 2
    assert outcome.artifacts[0].suffix == ".json"
    assert outcome.artifacts[1].suffix == ".pdf"
    assert writer.binary_writes == [
        (tmp_path / "store_performance_analysis.pdf", b"%PDF-1.4 test")
    ]
    assert outcome.warnings == ()


def test_pdf_failure_keeps_json_and_marks_stage_partial(tmp_path: Path) -> None:
    outcome, writer = _run_stage(
        tmp_path,
        workload=None,
        pdf_renderer=_FakePdfRenderer(fail=True),
    )

    assert outcome.status is StageStatus.PARTIAL
    assert len(writer.writes) == 1
    assert writer.binary_writes == []
    assert outcome.artifacts == (tmp_path / "store_performance_analysis.json",)
    assert len(outcome.warnings) == 1
    assert "Font is unavailable" in outcome.warnings[0]
    assert outcome.payload is not None
    assert outcome.payload.status is PerformanceAnalysisStatus.UNAVAILABLE
