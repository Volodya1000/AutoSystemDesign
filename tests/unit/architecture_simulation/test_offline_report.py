"""Verify offline simulation outcomes, evidence and real report artifacts."""

import json
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader

from application.architecture_simulation.offline import (
    OfflineSimulationConfigurationError,
    OfflineSimulationRunner,
)
from application.architecture_simulation.trace_report import forward_path_quantiles
from domain.architecture_simulation.offline import (
    OfflineSimulationInput,
    OfflineSimulationResult,
)
from domain.architecture_simulation.report import (
    LatencyQuantiles,
    RequirementKind,
    RequirementVerdict,
    SimulationReportStatus,
)
from domain.models.requirements import ResourceUtilizationRequirement
from infrastructure.architecture_simulation.linear_graph_engine import (
    SimPyLinearGraphEngine,
)
from scripts.run_offline_simulation_demo import main

pytestmark: pytest.MarkDecorator = pytest.mark.unit
_INPUT_PATH: Path = (
    Path(__file__).resolve().parents[3] / "examples" / "simulation" / "cache_demo.json"
)


@pytest.fixture(name="demo_inputs")
def fixture_demo_inputs() -> OfflineSimulationInput:
    return OfflineSimulationInput.model_validate_json(
        _INPUT_PATH.read_text(encoding="utf-8")
    )


@pytest.mark.parametrize(
    ("durations", "expected"),
    [
        ([], (None, None, None)),
        ([0.085], (85.0, 85.0, 85.0)),
        ([0.085, 0.135, 0.185], (135.0, 180.0, 184.0)),
    ],
)
def test_descriptive_quantiles_preserve_empty_and_small_samples(
    durations: list[float], expected: tuple[float | None, float | None, float | None]
) -> None:
    result: LatencyQuantiles = forward_path_quantiles(durations)
    assert (result.p50, result.p95, result.p99) == pytest.approx(expected)


def test_fixed_graph_has_known_capacity_and_no_disappearing_requests(
    demo_inputs: OfflineSimulationInput,
) -> None:
    result: OfflineSimulationResult = OfflineSimulationRunner(
        SimPyLinearGraphEngine()
    ).run(demo_inputs)

    assert result.report.status == SimulationReportStatus.PARTIAL
    assert [
        (
            run.generated_requests,
            run.completed_requests,
            run.rejected_requests,
            run.unfinished_requests,
        )
        for run in result.report.experiments
    ] == [(100, 100, 0, 0), (800, 199, 595, 6)]
    assert all(
        evaluation.status == RequirementVerdict.NOT_EVALUATED
        for evaluation in result.report.requirements
    )
    assert all(
        run.client_latency_milliseconds == LatencyQuantiles()
        for run in result.report.experiments
    )
    assert {
        rejection.node_identifier
        for run in result.observations
        for rejection in run.result.rejections
    } == {"api"}


def test_repeated_offline_runs_preserve_unrounded_json_evidence(
    demo_inputs: OfflineSimulationInput,
) -> None:
    runner: OfflineSimulationRunner = OfflineSimulationRunner(SimPyLinearGraphEngine())
    first: OfflineSimulationResult = runner.run(demo_inputs)
    second: OfflineSimulationResult = runner.run(demo_inputs)

    assert first == second
    assert OfflineSimulationResult.model_validate_json(first.model_dump_json()) == first


def test_unsupported_interval_preserves_bounds_instead_of_inventing_zero(
    demo_inputs: OfflineSimulationInput,
) -> None:
    demo_inputs.scenario.requirements.append(
        ResourceUtilizationRequirement(minimum_value=20, maximum_value=80)
    )
    result: OfflineSimulationResult = OfflineSimulationRunner(
        SimPyLinearGraphEngine()
    ).run(demo_inputs)

    for evaluation in result.report.requirements:
        if evaluation.type_identifier == RequirementKind.RESOURCE_UTILIZATION:
            assert evaluation.threshold_value is None
            assert evaluation.minimum_value == 20
            assert evaluation.maximum_value == 80
            assert evaluation.status == RequirementVerdict.NOT_EVALUATED


@pytest.mark.parametrize(
    "changes",
    [{"replications": 2}, {"warmup_seconds": 1}, {"max_events_per_replication": 1}],
)
def test_unsupported_demo_configuration_fails_explicitly(
    demo_inputs: OfflineSimulationInput, changes: dict[str, int]
) -> None:
    demo_inputs.configuration = demo_inputs.configuration.model_copy(update=changes)

    with pytest.raises(OfflineSimulationConfigurationError):
        OfflineSimulationRunner(SimPyLinearGraphEngine()).run(demo_inputs)


def test_cli_generates_real_json_trace_and_searchable_pdf(tmp_path: Path) -> None:
    assert main(["--input", str(_INPUT_PATH), "--output-dir", str(tmp_path)]) == 0

    report: dict[str, object] = json.loads(
        (tmp_path / "offline_cache_simulation.json").read_text(encoding="utf-8")
    )
    evidence: OfflineSimulationResult = OfflineSimulationResult.model_validate_json(
        (tmp_path / "offline_cache_simulation_trace.json").read_text(encoding="utf-8")
    )
    reader: PdfReader = PdfReader(
        BytesIO((tmp_path / "offline_cache_simulation.pdf").read_bytes())
    )
    text: str = "\n".join(page.extract_text() for page in reader.pages)

    assert report == evidence.report.model_dump(mode="json")
    assert len(reader.pages) >= 1
    assert all(
        identifier in text.split() for identifier in ("client", "api", "cache", "db")
    )
    assert "335.00" in text.split()
    assert "595" in text.split()
