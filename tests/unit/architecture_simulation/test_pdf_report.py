"""Protect the information an architect needs to interpret a simulation PDF."""

from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader
from reportlab.graphics.shapes import Rect, String

from application.architecture_simulation.graph_mapper import (
    ArchitectureSimulationPlanMapper,
)
from application.architecture_simulation.offline import OfflineSimulationRunner
from application.architecture_simulation.trace_report import GraphTraceReportBuilder
from domain.architecture_simulation.offline import (
    OfflineSimulationInput,
    OfflineSimulationResult,
)
from domain.architecture_simulation.report import (
    ConfidenceInterval,
    RequirementEvaluation,
    RequirementKind,
    RequirementVerdict,
    SimulationReport,
    SimulationReportStatus,
    SimulationWorkload,
)
from domain.models.enums import Operator
from domain.models.nodes import ClientNode
from domain.models.requirements import LatencyRequirement
from domain.models.topology import ArchitectureGraph
from infrastructure.architecture_simulation.linear_graph_engine import (
    SimPyLinearGraphEngine,
)
from infrastructure.architecture_simulation.pdf_graph import graph_drawing
from infrastructure.architecture_simulation.pdf_report import (
    SimulationReportPdfRenderer,
)
from infrastructure.reporting.pdf.typography import UnicodeReportFont
from tests.unit.architecture_simulation.factories import (
    make_compute,
    make_edge,
    make_graph,
    make_scenario,
)

pytestmark = pytest.mark.unit


@pytest.fixture(name="result")
def fixture_result() -> OfflineSimulationResult:
    source = Path(__file__).resolve().parents[3] / "examples/simulation/cache_demo.json"
    inputs = OfflineSimulationInput.model_validate_json(source.read_text())
    return OfflineSimulationRunner(SimPyLinearGraphEngine()).run(inputs)


def _pdf_text(result: OfflineSimulationResult) -> str:
    reader = PdfReader(BytesIO(SimulationReportPdfRenderer().render(result)))
    return "\n".join(page.extract_text() for page in reader.pages)


def test_summary_identifies_rejecting_node_and_next_experiment(
    result: OfflineSimulationResult,
) -> None:
    text = _pdf_text(result)
    assert "Отказы на узле api" in text
    assert "595" in text
    assert "74.38%" in text
    assert "19.90" in text
    assert "сервисной емкостью" in text
    assert "Посещения узлов" not in text


def test_report_keeps_unmodeled_timeout_distinct_from_zero(
    result: OfflineSimulationResult,
) -> None:
    assert result.report.timeouts_modeled is False
    assert all(run.timed_out_requests is None for run in result.report.experiments)
    text = _pdf_text(result)
    assert text.count("Таймауты не моделируются") == 1
    assert "не измерено" in text


def test_targets_and_operators_survive_report_and_pdf(
    result: OfflineSimulationResult,
) -> None:
    requirement: LatencyRequirement = next(
        item
        for item in result.inputs.scenario.requirements
        if isinstance(item, LatencyRequirement)
    )
    requirement.operator = Operator.LESS_THAN
    result.report = GraphTraceReportBuilder().build(result.inputs, result.observations)
    assert result.report.requirements[0].operator is Operator.LESS_THAN
    text = _pdf_text(result)
    assert "p99 < 100 мс" in text
    assert "99.9 %" in text
    assert text.count("полный ответ не") == 1


def test_distinct_latency_targets_remain_distinguishable(
    result: OfflineSimulationResult,
) -> None:
    requirement = result.report.requirements[0]
    result.report.requirements.append(
        requirement.model_copy(
            update={
                "requirement_index": 2,
                "threshold_value": 200.0,
                "percentile": 95.0,
            }
        )
    )
    text = _pdf_text(result)
    assert "#1 Задержка p99" in text
    assert "#3 Задержка p95" in text
    assert "200 мс" in text


def test_linear_graph_does_not_receive_cache_claims(
    result: OfflineSimulationResult,
) -> None:
    result.inputs.graph = make_graph()
    result.inputs.scenario = make_scenario()
    linear = OfflineSimulationRunner(SimPyLinearGraphEngine()).run(result.inputs)
    text = _pdf_text(linear)
    assert "промах" not in text
    assert "Кэш не вызывает" not in text


def test_empty_cohort_has_missing_ratios_and_no_invented_latency(
    result: OfflineSimulationResult,
) -> None:
    for run in result.observations:
        run.result = run.result.model_copy(
            update={
                "observations": [],
                "rejections": [],
                "measured_arrivals": 0,
                "unfinished": 0,
            }
        )
    result.report = GraphTraceReportBuilder().build(result.inputs, result.observations)
    assert all(run.rejected_ratio is None for run in result.report.experiments)
    assert all(run.unfinished_ratio is None for run in result.report.experiments)
    assert "нет данных" in _pdf_text(result)


def test_conclusive_requirement_keeps_its_evidence(
    result: OfflineSimulationResult,
) -> None:
    requirement = RequirementEvaluation(
        requirement_index=0,
        type_identifier=RequirementKind.LATENCY,
        phase=SimulationWorkload.PEAK,
        operator=Operator.LESS_THAN_OR_EQUAL,
        threshold_value=100,
        percentile=99,
        observed_value=0.995,
        confidence_interval=ConfidenceInterval(
            lower=0.991,
            upper=0.999,
            confidence_level=0.95,
            method="independent_replications",
        ),
        status=RequirementVerdict.MET,
    )
    result.report.requirements = [requirement]
    text = _pdf_text(result)
    assert "0.995" in text
    assert "0.991" in text
    assert "0.999" in text
    assert "independent_replications" in text


@pytest.mark.parametrize("shape", ["chain", "alternatives"])
def test_topology_cards_do_not_overlap(shape: str) -> None:
    identifiers = [f"service_{index}" for index in range(6)]
    pairs = (
        list(zip(["web", *identifiers[:-1]], identifiers, strict=True))
        if shape == "chain"
        else [("web", identifier) for identifier in identifiers]
    )
    graph = ArchitectureGraph(
        nodes=[ClientNode(identifier="web"), *map(make_compute, identifiers)],
        edges=[make_edge(source, target) for source, target in pairs],
    )
    plan = ArchitectureSimulationPlanMapper().map(graph, make_scenario())
    drawing = graph_drawing(plan, 493, UnicodeReportFont().register())
    cards = [item for item in drawing.contents if isinstance(item, Rect)]
    for index, first in enumerate(cards):
        for second in cards[index + 1 :]:
            overlap_x = min(first.x + first.width, second.x + second.width)
            overlap_x -= max(first.x, second.x)
            overlap_y = min(first.y + first.height, second.y + second.height)
            overlap_y -= max(first.y, second.y)
            assert min(overlap_x, overlap_y) <= 0


def test_long_identifiers_wrap_without_shrinking_text() -> None:
    identifier = "ОченьДлинныйИдентификаторСервиса" * 3
    graph = ArchitectureGraph(
        nodes=[ClientNode(identifier="web"), make_compute(identifier=identifier)],
        edges=[make_edge("web", identifier)],
    )
    plan = ArchitectureSimulationPlanMapper().map(graph, make_scenario())
    drawing = graph_drawing(plan, 493, UnicodeReportFont().register())
    labels = [item for item in drawing.contents if isinstance(item, String)]
    assert len(labels) > 2
    assert all(item.fontSize == 9 for item in labels)


def test_unavailable_report_uses_its_real_status(
    result: OfflineSimulationResult,
) -> None:
    result.report = SimulationReport(
        scenario_identifier="missing",
        status=SimulationReportStatus.UNAVAILABLE,
    )
    text = _pdf_text(result)
    assert "расчет недоступен" in text
    assert "частичное покрытие" not in text
