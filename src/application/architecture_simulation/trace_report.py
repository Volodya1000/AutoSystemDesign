"""Summarize completed forward paths without declaring end-to-end SLOs."""

from __future__ import annotations

from collections import Counter
from statistics import quantiles
from typing import TYPE_CHECKING

from domain.architecture_simulation.report import (
    LatencyQuantiles,
    NodeSimulationMetrics,
    RequirementEvaluation,
    RequirementKind,
    RequirementVerdict,
    SimulationExperiment,
    SimulationFinding,
    SimulationFindingCode,
    SimulationLimitation,
    SimulationLimitationCode,
    SimulationReasonCode,
    SimulationReport,
    SimulationReportStatus,
    SimulationWorkload,
)
from domain.models.base_constraints import (
    PercentileThresholdRequirement,
    ThresholdRequirement,
)
from domain.models.requirements import (
    AvailabilityRequirement,
    LatencyRequirement,
    Requirement,
    ResourceUtilizationRequirement,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain.architecture_simulation.offline import (
        OfflineSimulationInput,
        WorkloadObservation,
    )
    from domain.models.enums import Operator


def forward_path_quantiles(durations_seconds: Sequence[float]) -> LatencyQuantiles:
    """Calculate descriptive inclusive quantiles of completed forward paths."""
    if not durations_seconds:
        return LatencyQuantiles()
    if len(durations_seconds) == 1:
        duration_ms: float = durations_seconds[0] * 1000.0
        return LatencyQuantiles(p50=duration_ms, p95=duration_ms, p99=duration_ms)
    percentiles: list[float] = quantiles(durations_seconds, n=100, method="inclusive")
    return LatencyQuantiles(
        p50=percentiles[49] * 1000.0,
        p95=percentiles[94] * 1000.0,
        p99=percentiles[98] * 1000.0,
    )


class GraphTraceReportBuilder:
    """Build the canonical partial report solely from observed root outcomes."""

    def build(
        self,
        inputs: OfflineSimulationInput,
        observations: Sequence[WorkloadObservation],
    ) -> SimulationReport:
        """Keep unavailable metrics null and unsupported requirements unevaluated."""
        experiments: list[SimulationExperiment] = [
            _experiment(run, inputs.configuration.measurement_seconds)
            for run in observations
        ]
        return SimulationReport(
            scenario_identifier=inputs.scenario.identifier,
            status=SimulationReportStatus.PARTIAL,
            configuration=inputs.configuration,
            timeouts_modeled=False,
            experiments=experiments,
            findings=[
                SimulationFinding(
                    code=SimulationFindingCode.REJECTED_REQUESTS,
                    severity="warning",
                    title=f"Отказы на узле {node.node_identifier}",
                    description=(
                        f"Нагрузка {run.offered_requests_per_second:g} запросов/с: "
                        "отклонено "
                        f"{node.rejected_requests} клиентских запросов. "
                        "Отказы ограничивают достигнутый темп завершений."
                    ),
                    affected_node_identifiers=[node.node_identifier],
                    recommendation=(
                        "Сравнить вариант с большей сервисной емкостью этого узла "
                        "при той же нагрузке. Увеличение только очереди "
                        "не увеличивает число обслуживающих каналов."
                    ),
                )
                for run in experiments
                for node in run.nodes
                if node.rejected_requests
            ],
            requirements=[
                _requirement(index, requirement, run.workload_id)
                for run in observations
                for index, requirement in enumerate(inputs.scenario.requirements)
            ],
            limitations=[
                SimulationLimitation(
                    code=SimulationLimitationCode.TIMEOUTS_UNMODELED,
                    description=(
                        "Таймауты связей не моделируются; число таймаутов "
                        "не измерено. Deadline не ограничивает completed."
                    ),
                ),
                SimulationLimitation(
                    code=SimulationLimitationCode.FORWARD_PATH_ONLY,
                    description=(
                        "Измеряется прямой путь запроса. Обратный путь ответа "
                        "и полная клиентская задержка не моделируются."
                    ),
                ),
                SimulationLimitation(
                    code=SimulationLimitationCode.DESCRIPTIVE_STATISTICS,
                    description=(
                        "p50/p95/p99 - описательные квантили завершённых запросов "
                        "одного прогона, без доверительных интервалов. Отказы и "
                        "незавершённые запросы показаны отдельно."
                    ),
                ),
                SimulationLimitation(
                    code=SimulationLimitationCode.PERIODIC_ARRIVALS,
                    description=(
                        "Запросы поступают равномерно в течение окна. Это "
                        "фиксированный пример, не пуассоновский поток. Нет "
                        "прогрева и дополнительного времени на завершение."
                    ),
                ),
            ],
        )


def _experiment(
    run: WorkloadObservation, measurement_seconds: float
) -> SimulationExperiment:
    visits: Counter[str] = Counter(
        identifier
        for observation in run.result.observations
        for identifier in observation.visited_resources
    )
    rejections: Counter[str] = Counter(
        rejection.node_identifier for rejection in run.result.rejections
    )
    return SimulationExperiment(
        workload_id=run.workload_id,
        offered_requests_per_second=run.offered_requests_per_second,
        generated_requests=run.result.measured_arrivals,
        completed_requests=len(run.result.observations),
        rejected_requests=len(run.result.rejections),
        unfinished_requests=run.result.unfinished,
        throughput_requests_per_second=(
            len(run.result.observations) / measurement_seconds
        ),
        rejected_ratio=(
            len(run.result.rejections) / run.result.measured_arrivals
            if run.result.measured_arrivals
            else None
        ),
        unfinished_ratio=(
            run.result.unfinished / run.result.measured_arrivals
            if run.result.measured_arrivals
            else None
        ),
        forward_path_latency_milliseconds=forward_path_quantiles(
            [item.traversal_seconds for item in run.result.observations]
        ),
        completed_root_node_visits=dict(sorted(visits.items())),
        nodes=[
            NodeSimulationMetrics(
                node_identifier=identifier,
                rejected_requests=rejections[identifier],
            )
            for identifier in sorted(visits.keys() | rejections.keys())
        ],
    )


def _requirement(
    index: int, requirement: Requirement, workload: SimulationWorkload
) -> RequirementEvaluation:
    kind: RequirementKind = RequirementKind(requirement.type_identifier)
    reason: SimulationReasonCode = SimulationReasonCode.REQUIREMENT_SCOPE_UNKNOWN
    operator: Operator | None = None
    threshold: float | None = None
    percentile: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    if isinstance(requirement, ThresholdRequirement):
        threshold = requirement.threshold_value
        operator = requirement.operator
    if isinstance(requirement, PercentileThresholdRequirement):
        percentile = requirement.percentile
    if isinstance(requirement, ResourceUtilizationRequirement):
        minimum = requirement.minimum_value
        maximum = requirement.maximum_value
    if isinstance(requirement, LatencyRequirement):
        reason = SimulationReasonCode.CLIENT_RESPONSE_UNMODELED
        threshold = requirement.threshold_value
        percentile = requirement.percentile
    elif isinstance(requirement, AvailabilityRequirement):
        reason = SimulationReasonCode.FAILURE_REPAIR_MODEL_MISSING
        threshold = requirement.threshold_value
    return RequirementEvaluation(
        requirement_index=index,
        type_identifier=kind,
        phase=workload,
        operator=operator,
        threshold_value=threshold,
        minimum_value=minimum,
        maximum_value=maximum,
        percentile=percentile,
        status=RequirementVerdict.NOT_EVALUATED,
        reason_code=reason,
    )
