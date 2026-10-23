"""Build concise decision and experiment sections from canonical results."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

from reportlab.platypus import Flowable, Paragraph

from domain.architecture_simulation.report import SimulationLimitationCode
from infrastructure.architecture_simulation.pdf_requirements import (
    PHASE_NAMES,
    requirement_rows,
)
from infrastructure.architecture_simulation.pdf_tables import (
    number_text,
    ratio_text,
    report_table,
)

if TYPE_CHECKING:
    from reportlab.lib.styles import ParagraphStyle

    from domain.architecture_simulation.offline import OfflineSimulationResult
    from domain.architecture_simulation.report import SimulationReport


def outcomes_rows(report: SimulationReport) -> list[list[str]]:
    """Keep losses beside completed-path latency and the offered workload."""
    rows: list[list[str]] = [
        [
            "Нагрузка / вход, запр./с",
            "Завершено/с",
            "Отказано",
            "Осталось",
            "p99, мс (n)",
        ]
    ]
    rows.extend(
        [
            f"{PHASE_NAMES[run.workload_id]} / {run.offered_requests_per_second:g}",
            number_text(run.throughput_requests_per_second),
            f"{ratio_text(run.rejected_ratio)} ({run.rejected_requests})",
            f"{ratio_text(run.unfinished_ratio)} ({run.unfinished_requests})",
            (
                f"{number_text(run.forward_path_latency_milliseconds.p99)} "
                f"({run.completed_requests})"
            ),
        ]
        for run in report.experiments
    )
    return rows


def decision_sections(
    report: SimulationReport, styles: dict[str, ParagraphStyle], width: float
) -> list[Flowable]:
    """Present the observed problem, target and next experiment first."""
    sections: list[Flowable] = []
    for finding in report.findings:
        sections.extend(
            [
                Paragraph(escape(finding.title), styles["finding"]),
                Paragraph(escape(finding.description), styles["body"]),
            ]
        )
        if finding.recommendation is not None:
            sections.append(Paragraph(escape(finding.recommendation), styles["note"]))
    sections.append(report_table(outcomes_rows(report), styles, width))
    sections.append(
        Paragraph(
            "p99 — оценка по завершенным прямым путям. Завершено/с — результат "
            "окна, не доказанная стационарная пропускная способность.",
            styles["note"],
        )
    )
    if report.requirements:
        sections.extend(
            [
                Paragraph("Цели и покрытие проверки", styles["heading"]),
                report_table(requirement_rows(report), styles, width),
            ]
        )
    return sections


def limitations_text(report: SimulationReport) -> str:
    """State each material scope limitation once without repeating verdicts."""
    covered: set[SimulationLimitationCode] = {
        SimulationLimitationCode.FORWARD_PATH_ONLY,
        SimulationLimitationCode.DESCRIPTIVE_STATISTICS,
        SimulationLimitationCode.PERIODIC_ARRIVALS,
        SimulationLimitationCode.TIMEOUTS_UNMODELED,
    }
    notes: list[str] = []
    codes: set[SimulationLimitationCode] = {item.code for item in report.limitations}
    if SimulationLimitationCode.DESCRIPTIVE_STATISTICS in codes:
        notes.append("Описательный прогон без доверительных интервалов.")
    if SimulationLimitationCode.PERIODIC_ARRIVALS in codes:
        notes.append("Равномерный вход; без прогрева и ожидания завершения после окна.")
    if report.timeouts_modeled is False:
        notes.append("Таймауты не моделируются; их число не измерено.")
    notes.extend(
        item.description for item in report.limitations if item.code not in covered
    )
    return " ".join(dict.fromkeys(notes))


def inputs_rows(result: OfflineSimulationResult) -> list[list[str]]:
    """Expose only resource parameters that affect this simulation."""
    rows: list[list[str]] = [
        [
            "Узел",
            "Реплики x каналы",
            "In-flight / очередь",
            "Сервис: среднее / std, мс",
            "Hit",
        ]
    ]
    rows.extend(
        [
            resource.identifier,
            f"{resource.replicas_count} x {resource.service_channels_per_replica}",
            (
                f"{resource.maximum_concurrency_per_replica} / "
                f"{resource.maximum_queue_size_per_replica}"
            ),
            (
                f"{resource.mean_service_seconds * 1000:g} / "
                f"{resource.std_service_seconds * 1000:g}"
            ),
            ratio_text(resource.cache_hit_probability)
            if resource.cache_hit_probability is not None
            else "—",
        ]
        for resource in result.plan.resources
    )
    return rows


def experiment_sections(
    result: OfflineSimulationResult, styles: dict[str, ParagraphStyle], width: float
) -> list[Flowable]:
    """Document the modeled parameters without printing raw event counters."""
    configuration = result.report.configuration
    links: str = "; ".join(
        f"{edge.source_identifier} → {edge.target_identifier}: "
        f"{edge.network_latency_seconds * 1000:g} мс, {edge.routing_mode.value}"
        for edge in result.plan.connections
    )
    return [
        Paragraph("Параметры эксперимента", styles["heading"]),
        report_table(inputs_rows(result), styles, width),
        Paragraph(
            f"Окно: {configuration.measurement_seconds:g} с; "
            f"повторов: {configuration.replications}; "
            f"прогрев: {configuration.warmup_seconds:g} с; "
            f"seed: {configuration.base_seed}.",
            styles["note"],
        ),
        Paragraph(
            "Очередь FIFO на реплику; выбор реплики round-robin. "
            "Сервис постоянный при нулевом стандартном отклонении, "
            "иначе Gamma по среднему и стандартному отклонению (std).",
            styles["note"],
        ),
        Paragraph(escape(links), styles["note"]),
    ]
