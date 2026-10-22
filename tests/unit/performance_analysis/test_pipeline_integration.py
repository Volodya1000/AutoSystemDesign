"""LLM-free end-to-end tests through C4 outcome, runner, JSON and real PDF."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pypdf import PdfReader

from application.pipeline.outcome import StageOutcome, StageStatus
from application.pipeline.runner import PipelineRunner
from application.pipeline.stage import StageId
from application.pipeline.stages.performance_analysis import PerformanceAnalysisStage
from domain.models.enums import EdgeRoutingMode, NodeType
from domain.models.scenarios import DesignScenario, WorkloadProfile
from domain.models.topology import ArchitectureGraph
from domain.performance_analysis.report import (
    PerformanceAnalysisReport,
    PerformanceAnalysisStatus,
    PerformanceFindingCode,
)
from infrastructure.performance_analysis.offline_c4_stage import OfflineC4Stage
from infrastructure.performance_analysis.pdf_renderer import (
    PerformanceReportPdfRenderer,
)
from infrastructure.persistence.artifact_writer import FileSystemArtifactWriter
from tests.factories import create_test_compute_node, create_test_edge, create_test_node

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


pytestmark = pytest.mark.unit


class _RecordingReporter:
    """Collect runner outcomes without logging or network calls."""

    def __init__(self) -> None:
        self.outcomes: list[StageOutcome[object]] = []

    def report(self, outcomes: Sequence[StageOutcome[object]]) -> None:
        self.outcomes = list(outcomes)


def _graph(*, mean_ms: float = 50.0, with_fanout: bool = False) -> ArchitectureGraph:
    """Build one known queueing example with an optional synchronous fan-out."""
    nodes = [
        create_test_node("client", NodeType.CLIENT),
        create_test_compute_node(
            "service",
            service_channels_per_replica=1,
            mean_ms=mean_ms,
            std_ms=mean_ms,
        ),
    ]
    edges = [create_test_edge("client", "service")]
    if with_fanout:
        nodes.append(
            create_test_compute_node(
                "analytics",
                service_channels_per_replica=1,
                mean_ms=5.0,
                std_ms=5.0,
            )
        )
        edges = [
            create_test_edge(
                "client",
                "service",
                routing_mode=EdgeRoutingMode.FAN_OUT,
            ),
            create_test_edge(
                "client",
                "analytics",
                routing_mode=EdgeRoutingMode.FAN_OUT,
            ),
        ]
    return ArchitectureGraph(nodes=nodes, edges=edges)


def _run(
    output_directory: Path,
    scenario: DesignScenario,
    graph: ArchitectureGraph,
) -> tuple[int, _RecordingReporter, PerformanceAnalysisReport]:
    """Execute the actual two-stage pipeline and read persisted JSON."""
    reporter = _RecordingReporter()
    pipeline = PipelineRunner(
        stages=[
            OfflineC4Stage(graph),
            PerformanceAnalysisStage(pdf_renderer=PerformanceReportPdfRenderer()),
        ],
        reporter=reporter,
    )
    result_code = pipeline.run(
        scenario,
        output_directory,
        FileSystemArtifactWriter(log_writes=False),
    )
    report_path = output_directory / f"{scenario.identifier}_performance_analysis.json"
    report = PerformanceAnalysisReport.model_validate_json(
        report_path.read_text(encoding="utf-8")
    )
    return result_code, reporter, report


def _scenario(
    identifier: str,
    peak_rps: float | None,
) -> DesignScenario:
    """Build peak-load scenarios while preserving explicit missing workload."""
    workload = (
        WorkloadProfile(
            baseline_requests_per_second=peak_rps,
            peak_requests_per_second=peak_rps,
        )
        if peak_rps is not None
        else None
    )
    return DesignScenario(
        identifier=identifier,
        description="Independent end-to-end queueing case",
        workload=workload,
    )


def test_linear_mm1_metrics_match_hand_calculation_in_json_and_pdf(
    tmp_path: Path,
) -> None:
    """At lambda=10, mu=20, calculate 50ms wait and 100ms response."""
    identifier = "linear"
    exit_code, reporter, report = _run(
        tmp_path,
        _scenario(identifier, 10.0),
        _graph(),
    )

    assert exit_code == 0
    assert [outcome.name for outcome in reporter.outcomes] == [
        StageId.C4,
        StageId.PERFORMANCE_ANALYSIS,
    ]
    assert all(outcome.status is StageStatus.SUCCEEDED for outcome in reporter.outcomes)
    assert report.status is PerformanceAnalysisStatus.PARTIAL
    service = next(node for node in report.nodes if node.node_identifier == "service")
    assert service.incoming_requests_per_second == pytest.approx(10.0)
    assert service.estimated_capacity_requests_per_second == pytest.approx(20.0)
    assert service.utilization_ratio == pytest.approx(0.5)
    assert service.estimated_mean_queue_wait_milliseconds == pytest.approx(50.0)
    assert service.estimated_mean_response_time_milliseconds == pytest.approx(100.0)
    assert report.estimated_longest_synchronous_path_mean_milliseconds == pytest.approx(
        101.0
    )
    assert report.critical_path_node_identifiers == ["client", "service"]
    reader = PdfReader(str(tmp_path / f"{identifier}_performance_analysis.pdf"))
    pdf_text = "\n".join(page.extract_text() for page in reader.pages)
    assert identifier in pdf_text
    assert "100.00" in pdf_text
    assert "101.00" in pdf_text
    assert "Начало пути" in pdf_text
    assert "Среднее время в узле: 100.00 мс" in pdf_text
    assert "Предупреждение" not in pdf_text
    assert (tmp_path / "architecture_graph.json").is_file()


def test_absent_workload_still_produces_json_and_pdf(tmp_path: Path) -> None:
    exit_code, reporter, report = _run(
        tmp_path,
        _scenario("no_workload", None),
        _graph(),
    )

    assert exit_code == 0
    assert reporter.outcomes[-1].status is StageStatus.SUCCEEDED
    assert report.status is PerformanceAnalysisStatus.UNAVAILABLE
    assert report.findings == []
    assert report.nodes[-1].estimated_mean_response_time_milliseconds is None
    assert (tmp_path / "no_workload_performance_analysis.pdf").is_file()


def test_overload_has_no_invented_steady_state_wait(tmp_path: Path) -> None:
    exit_code, reporter, report = _run(
        tmp_path,
        _scenario("overloaded", 30.0),
        _graph(),
    )

    service = next(node for node in report.nodes if node.node_identifier == "service")
    capacity_codes = {
        item.finding_code
        for item in report.findings
        if "service" in item.affected_node_identifiers
    }
    assert exit_code == 0
    assert reporter.outcomes[-1].status is StageStatus.SUCCEEDED
    assert service.utilization_ratio == pytest.approx(1.5)
    assert service.estimated_mean_queue_wait_milliseconds is None
    assert service.estimated_mean_response_time_milliseconds is None
    assert PerformanceFindingCode.CAPACITY_SATURATION in capacity_codes
    assert PerformanceFindingCode.CAPACITY_HEADROOM not in capacity_codes


def test_two_runs_in_separate_directories_keep_their_own_results(
    tmp_path: Path,
) -> None:
    stable_dir = tmp_path / "stable"
    overloaded_dir = tmp_path / "overloaded"

    _, _, first = _run(
        stable_dir,
        _scenario("one", 10.0),
        _graph(with_fanout=True),
    )
    _, _, second = _run(
        overloaded_dir,
        _scenario("two", 30.0),
        _graph(),
    )

    assert first.scenario_identifier == "one"
    assert second.scenario_identifier == "two"
    assert len(first.nodes) == 3
    assert len(second.nodes) == 2
    assert (stable_dir / "one_performance_analysis.pdf").is_file()
    assert (overloaded_dir / "two_performance_analysis.pdf").is_file()
    assert not (stable_dir / "two_performance_analysis.json").exists()
