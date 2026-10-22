"""Typed evidence for checking nonfunctional requirements."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RequirementCheckStatus(StrEnum):
    """Result of checking exactly one nonfunctional requirement."""

    # Одно требование: проверка выполнена, порог соблюдён.
    SATISFIED = "satisfied"

    # Одно требование: проверка выполнена, порог нарушен.
    VIOLATED = "violated"

    # Одно требование: достоверной проверки не было, вывод делать нельзя.
    NOT_EVALUATED = "not_evaluated"


class RequirementCheckReason(StrEnum):
    """Explain why an NFR check produced NOT_EVALUATED, not a failure verdict.

    This is one primary reason, not a complete list of missing prerequisites.
    The requirement's type_identifier already identifies the unsupported metric.
    """

    # Нет зарегистрированного валидатора для этого типа требования.
    # Например, проверка availability пока не реализована.
    NO_VALIDATOR = "no_validator"

    # Не задан workload для требования, зависящего от нагрузки.
    # Важно: добавление workload само по себе не создаёт отсутствующий валидатор.
    MISSING_WORKLOAD = "missing_workload"

    # Нет результата валидации: например, LLM не выдала разбираемый C4-граф.
    GRAPH_UNAVAILABLE = "graph_unavailable"

    # Граф оценивали, но саму архитектуру не приняли из-за других ошибок.
    # Даже успешная проверка бюджета такого графа не доказывает пригодность проекта.
    GRAPH_UNACCEPTED = "graph_unaccepted"

    # Внутренняя ошибка сопоставления: два результата с одним ID или несовпадение
    # типа результата и требования. Нельзя выбирать один результат наугад.
    INVALID_EVIDENCE = "invalid_evidence"


class RequirementAssessment(BaseModel):
    """One assessment for one occurrence in the original scenario list.

    The index-based identifier is local to the scenario, not a globally
    stable ID. Matching by type alone would collapse duplicate requirements.
    """

    model_config = ConfigDict(extra="forbid")

    requirement_identifier: str = Field(min_length=1)
    type_identifier: str = Field(min_length=1)
    status: RequirementCheckStatus
    reason: RequirementCheckReason | None = None
    validator_identifier: str | None = None

    @classmethod
    def not_evaluated(
        cls,
        *,
        identifier: str,
        kind: str,
        reason: RequirementCheckReason,
    ) -> "RequirementAssessment":
        """Explicit diagnostic for an unsupported or unavailable check."""
        return cls(
            requirement_identifier=identifier,
            type_identifier=kind,
            status=RequirementCheckStatus.NOT_EVALUATED,
            reason=reason,
        )


class RequirementCoverageStatus(StrEnum):
    """Aggregate NFR coverage across the entire scenario, not a single check.

    A separate enum excludes invalid combinations: a single check cannot be
    INCOMPLETE, and the aggregate cannot be NOT_EVALUATED.
    """

    # Все требования проверены и выполнены.
    SATISFIED = "satisfied"

    # Хотя бы одно требование нарушено; другие могут быть не проверены.
    VIOLATED = "violated"

    # Нарушений не найдено, но хотя бы одно требование не проверено.
    INCOMPLETE = "incomplete"

    # В сценарии нет нефункциональных требований.
    NOT_APPLICABLE = "not_applicable"


class RequirementCoverageReport(BaseModel):
    """Independent artifact: does not change performance report schema v1."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    scenario_identifier: str = Field(min_length=1)
    graph_accepted: bool
    status: RequirementCoverageStatus
    requirements: list[RequirementAssessment] = Field(default_factory=list)


def requirement_identifier(index: int) -> str:
    """Address a requirement occurrence within one immutable scenario version."""
    return f"requirements[{index}]"
