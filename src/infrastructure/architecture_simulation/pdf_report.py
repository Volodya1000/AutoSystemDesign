"""Render the program's canonical simulation values without recalculation."""

from __future__ import annotations

from html import escape
from io import BytesIO
from typing import TYPE_CHECKING

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
)

from domain.architecture_simulation.report import (
    RequirementEvaluation,
    RequirementKind,
    RequirementVerdict,
    SimulationReasonCode,
    SimulationReport,
    SimulationWorkload,
)
from infrastructure.architecture_simulation.pdf_graph import graph_drawing
from infrastructure.reporting.pdf.typography import (
    UnicodeReportFont,
    build_report_styles,
    draw_report_footer,
)

if TYPE_CHECKING:
    from reportlab.lib.styles import ParagraphStyle

    from domain.architecture_simulation.offline import OfflineSimulationResult

_WIDTH: float = A4[0] - 36 * mm
_PHASE_NAMES: dict[SimulationWorkload, str] = {
    SimulationWorkload.BASELINE: "Обычная",
    SimulationWorkload.PEAK: "Пиковая",
}
_REQUIREMENT_NAMES: dict[RequirementKind, str] = {
    RequirementKind.LATENCY: "задержка",
    RequirementKind.AVAILABILITY: "доступность",
    RequirementKind.BUDGET: "бюджет",
    RequirementKind.QUEUE_SIZE_PERCENTILE: "размер очереди",
    RequirementKind.RESOURCE_UTILIZATION: "загрузка ресурсов",
}
_VERDICT_NAMES: dict[RequirementVerdict, str] = {
    RequirementVerdict.MET: "выполнено",
    RequirementVerdict.VIOLATED: "нарушено",
    RequirementVerdict.INCONCLUSIVE: "недостаточно доказательств",
    RequirementVerdict.NOT_EVALUATED: "не оценено",
}
_REASON_NAMES: dict[SimulationReasonCode, str] = {
    SimulationReasonCode.CLIENT_RESPONSE_UNMODELED: (
        "обратный путь ответа не моделируется"
    ),
    SimulationReasonCode.FAILURE_REPAIR_MODEL_MISSING: (
        "нет модели отказов и восстановления"
    ),
    SimulationReasonCode.REQUIREMENT_SCOPE_UNKNOWN: (
        "недостаточно измерений для требования"
    ),
}


def _reason(code: SimulationReasonCode | None) -> str:
    """Translate technical reason codes for report readers."""
    if code is None:
        return "недостаточно данных"
    return _REASON_NAMES.get(code, "модель пока не поддерживает эту проверку")


def _number(value: float | None) -> str:
    """Distinguish an unavailable measurement from an observed zero."""
    return "нет данных" if value is None else f"{value:.2f}"


def _requirement_text(requirement: RequirementEvaluation) -> str:
    """Present the actual canonical verdict without inventing an outcome."""
    description: str = (
        f"{_PHASE_NAMES[requirement.phase]} нагрузка, "
        f"{_REQUIREMENT_NAMES[requirement.type_identifier]}: "
        f"{_VERDICT_NAMES[requirement.status]}"
    )
    if requirement.reason_code is not None:
        description += " - " + _reason(requirement.reason_code)
    return description + "."


def _table(rows: list[list[str]], styles: dict[str, ParagraphStyle]) -> LongTable:
    """Wrap cells consistently and keep headers on subsequent pages."""
    cells: list[list[Paragraph]] = [
        [Paragraph(escape(cell), styles["cell"]) for cell in row] for row in rows
    ]
    table: LongTable = LongTable(
        cells, colWidths=[_WIDTH / len(rows[0])] * len(rows[0]), repeatRows=1
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF0F6")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#BDCAD8")),
            ]
        )
    )
    return table


class SimulationReportPdfRenderer:
    """Present observed forward paths and explicit gaps in model coverage."""

    def render(self, result: OfflineSimulationResult) -> bytes:
        """Return the same report as JSON in a human-readable PDF layout."""
        font: str = UnicodeReportFont().register()
        styles: dict[str, ParagraphStyle] = build_report_styles(font)
        report: SimulationReport = result.report
        buffer: BytesIO = BytesIO()
        document: SimpleDocTemplate = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=16 * mm,
            bottomMargin=18 * mm,
            title=f"SimPy: {report.scenario_identifier}",
            author="AutoSystemDesign",
        )
        story: list[Flowable] = [
            Paragraph("Имитационный анализ SimPy", styles["title"]),
            Paragraph(escape(result.inputs.scenario.description), styles["body"]),
            Paragraph(
                "Статус: частичный результат. Расчёт выполнен без LLM по C4-графу. "
                "Это модель архитектуры, а не измерение работающих сервисов.",
                styles["body"],
            ),
            graph_drawing(result.plan, _WIDTH, font),
            Paragraph(
                "Кэш не вызывает базу. API обращается к БД только при промахе "
                "кэша; физические связи показаны на схеме.",
                styles["note"],
            ),
            Paragraph("Входные параметры", styles["heading"]),
            _inputs_table(result, styles),
            Paragraph("Учёт клиентских запросов", styles["heading"]),
            _outcomes_table(report, styles),
            Spacer(1, 3 * mm),
            Paragraph(
                "Поступило = завершено + отказано + осталось в работе. "
                "Окно заканчивается без ожидания незавершённых запросов.",
                styles["note"],
            ),
        ]
        story.extend(
            Paragraph(escape(finding.description), styles["body"])
            for finding in report.findings
        )
        story.extend(
            [
                PageBreak(),
                Paragraph("Задержки и ограничения", styles["title"]),
                _latency_table(report, styles),
                Paragraph(
                    "Показанные задержки относятся только к завершённым запросам "
                    "и прямому пути. p95 означает: 95% этих наблюдений не больше "
                    "указанного значения. Это не доказательство выполнения SLA.",
                    styles["body"],
                ),
                Paragraph("Посещения узлов завершёнными запросами", styles["heading"]),
                _visits_table(report, styles),
                Paragraph("Проверка требований", styles["heading"]),
            ]
        )
        story.extend(
            Paragraph(
                escape(_requirement_text(requirement)),
                styles["body"],
            )
            for requirement in report.requirements
        )
        story.extend(
            Paragraph(escape(limitation.description), styles["body"])
            for limitation in report.limitations
        )
        story.append(
            Paragraph(
                f"Seed: {report.configuration.base_seed}. "
                f"Окно: {report.configuration.measurement_seconds:g} с. "
                "Временные средние очередей, utilization и доверительные "
                "интервалы пока не вычисляются.",
                styles["note"],
            )
        )
        document.build(
            story,
            onFirstPage=lambda canvas, _doc: draw_report_footer(canvas, font),
            onLaterPages=lambda canvas, _doc: draw_report_footer(canvas, font),
        )
        return buffer.getvalue()


def _inputs_table(
    result: OfflineSimulationResult, styles: dict[str, ParagraphStyle]
) -> LongTable:
    rows: list[list[str]] = [
        ["Узел", "Реплики", "Каналы / реплика", "Сервис, мс", "Мест в очереди"]
    ]
    rows.extend(
        [
            resource.identifier,
            str(resource.replicas_count),
            str(resource.service_channels_per_replica),
            _number(resource.mean_service_seconds * 1000.0),
            str(resource.maximum_queue_size_per_replica),
        ]
        for resource in result.plan.resources
    )
    return _table(rows, styles)


def _outcomes_table(
    report: SimulationReport, styles: dict[str, ParagraphStyle]
) -> LongTable:
    rows: list[list[str]] = [
        ["Нагрузка", "Запр./с", "Поступило", "Завершено", "Отказано", "Осталось"]
    ]
    rows.extend(
        [
            _PHASE_NAMES[run.workload_id],
            _number(run.offered_requests_per_second),
            str(run.generated_requests),
            str(run.completed_requests),
            str(run.rejected_requests),
            str(run.unfinished_requests),
        ]
        for run in report.experiments
    )
    return _table(rows, styles)


def _latency_table(
    report: SimulationReport, styles: dict[str, ParagraphStyle]
) -> LongTable:
    rows: list[list[str]] = [["Прямой путь", "p50, мс", "p95, мс", "p99, мс"]]
    rows.extend(
        [
            _PHASE_NAMES[run.workload_id],
            _number(run.forward_path_latency_milliseconds.p50),
            _number(run.forward_path_latency_milliseconds.p95),
            _number(run.forward_path_latency_milliseconds.p99),
        ]
        for run in report.experiments
    )
    return _table(rows, styles)


def _visits_table(
    report: SimulationReport, styles: dict[str, ParagraphStyle]
) -> LongTable:
    identifiers: list[str] = sorted(
        {
            identifier
            for run in report.experiments
            for identifier in run.completed_root_node_visits
        }
    )
    rows: list[list[str]] = [["Нагрузка", *identifiers]]
    rows.extend(
        [
            _PHASE_NAMES[run.workload_id],
            *[str(run.completed_root_node_visits.get(key, 0)) for key in identifiers],
        ]
        for run in report.experiments
    )
    return _table(rows, styles)
