"""Present distinct requirement targets and group identical coverage gaps."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.architecture_simulation.report import (
    RequirementEvaluation,
    RequirementKind,
    RequirementVerdict,
    SimulationReasonCode,
    SimulationWorkload,
)

if TYPE_CHECKING:
    from domain.architecture_simulation.report import SimulationReport

PHASE_NAMES: dict[SimulationWorkload, str] = {
    SimulationWorkload.BASELINE: "Обычная",
    SimulationWorkload.PEAK: "Пиковая",
}
_NAMES: dict[RequirementKind, tuple[str, str]] = {
    RequirementKind.LATENCY: ("Задержка", "мс"),
    RequirementKind.AVAILABILITY: ("Доступность", "%"),
    RequirementKind.BUDGET: ("Бюджет", "USD/мес."),
    RequirementKind.QUEUE_SIZE_PERCENTILE: ("Очередь", "запросов"),
    RequirementKind.RESOURCE_UTILIZATION: ("Загрузка", "%"),
}
_VERDICTS: dict[RequirementVerdict, str] = {
    RequirementVerdict.MET: "выполнено",
    RequirementVerdict.VIOLATED: "нарушено",
    RequirementVerdict.INCONCLUSIVE: "недостаточно доказательств",
    RequirementVerdict.NOT_EVALUATED: "не оценено",
}
_REASONS: dict[SimulationReasonCode, str] = {
    SimulationReasonCode.CLIENT_RESPONSE_UNMODELED: "полный ответ не моделируется",
    SimulationReasonCode.FAILURE_REPAIR_MODEL_MISSING: "нет модели отказов",
    SimulationReasonCode.REQUIREMENT_SCOPE_UNKNOWN: "область проверки не определена",
    SimulationReasonCode.INSUFFICIENT_STATISTICAL_EVIDENCE: "недостаточно статистики",
}


def requirement_target(requirement: RequirementEvaluation) -> str:
    """Preserve identity, operator, percentile and units of the input goal."""
    name: str
    unit: str
    name, unit = _NAMES[requirement.type_identifier]
    label: str = f"#{requirement.requirement_index + 1} {name}"
    if requirement.percentile is not None:
        label += f" p{requirement.percentile:g}"
    if requirement.threshold_value is not None:
        operator: str = (
            requirement.operator.value if requirement.operator is not None else "?"
        )
        return f"{label} {operator} {requirement.threshold_value:g} {unit}"
    if requirement.minimum_value is not None and requirement.maximum_value is not None:
        return (
            f"{label}: {requirement.minimum_value:g}"
            f"–{requirement.maximum_value:g} {unit}"
        )
    return label


def _verdict_text(requirement: RequirementEvaluation) -> str:
    """Keep the actual observation and confidence bounds beside the verdict."""
    verdict: str = _VERDICTS[requirement.status]
    if requirement.reason_code is not None:
        verdict += ": " + _REASONS.get(
            requirement.reason_code, "модель не поддерживает проверку"
        )
    if requirement.observed_value is not None:
        verdict += f"; оценка {requirement.observed_value:g}"
    interval = requirement.confidence_interval
    if interval is not None:
        verdict += (
            f"; ДИ доли {interval.confidence_level:.0%}: "
            f"{interval.lower:g}–{interval.upper:g} ({interval.method})"
        )
    return verdict


def requirement_rows(report: SimulationReport) -> list[list[str]]:
    """Group equivalent workload verdicts without hiding different targets."""
    grouped: dict[tuple[str, str], list[str]] = {}
    for requirement in report.requirements:
        verdict: str = _verdict_text(requirement)
        key: tuple[str, str] = (requirement_target(requirement), verdict)
        phase: str = PHASE_NAMES[requirement.phase]
        if phase not in grouped.setdefault(key, []):
            grouped[key].append(phase)
    return [["Требование", "Нагрузка", "Результат"]] + [
        [target, ", ".join(phases), verdict]
        for (target, verdict), phases in grouped.items()
    ]
