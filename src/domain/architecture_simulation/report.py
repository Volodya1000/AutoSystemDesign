"""Define the JSON contract for discrete-event architecture simulation.

No statistics are computed here. Simulation engines and report builders are
responsible for populating these fields from measured *model* events.
"""

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from domain.architecture_simulation.configuration import SimulationConfiguration


class SimulationReportStatus(StrEnum):
    """Describe model coverage, not the status of the pipeline stage."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class RequirementVerdict(StrEnum):
    """Distinguish statistical non-decisions from unsupported requirements."""

    MET = "met"
    VIOLATED = "violated"
    INCONCLUSIVE = "inconclusive"
    NOT_EVALUATED = "not_evaluated"


class SimulationWorkload(StrEnum):
    """Keep stationary baseline and peak experiments separate."""

    BASELINE = "baseline"
    PEAK = "peak"


class RequirementKind(StrEnum):
    """Mirror the supported input requirement discriminators for reporting."""

    LATENCY = "latency"
    QUEUE_SIZE_PERCENTILE = "queue_size_percentile"
    BUDGET = "budget"
    AVAILABILITY = "availability"
    RESOURCE_UTILIZATION = "resource_utilization"


class SimulationReasonCode(StrEnum):
    """Identify why an experiment or a requirement could not be confirmed."""

    INSUFFICIENT_STATISTICAL_EVIDENCE = "insufficient_statistical_evidence"
    FAILURE_REPAIR_MODEL_MISSING = "failure_repair_model_missing"
    WORKLOAD_MISSING = "workload_missing"
    SERVICE_CHANNELS_UNKNOWN = "service_channels_unknown"
    UNSUPPORTED_GRAPH_SEMANTICS = "unsupported_graph_semantics"
    REQUIREMENT_SCOPE_UNKNOWN = "requirement_scope_unknown"


class SimulationFindingCode(StrEnum):
    """Stable finding categories; text is a separate representation."""

    QUEUE_BOTTLENECK = "queue_bottleneck"
    REJECTED_REQUESTS = "rejected_requests"
    WORKLOAD_MISSING = "workload_missing"
    UNSUPPORTED_MODEL = "unsupported_model"


class SimulationLimitationCode(StrEnum):
    """Stable labels for disclosed assumptions and coverage restrictions."""

    MODELED_NOT_MEASURED = "modeled_not_measured"
    UNMODELED_AVAILABILITY = "unmodeled_availability"
    UNSUPPORTED_GRAPH = "unsupported_graph"


class SimulationDataModel(BaseModel):
    """Reject accidental report-shape changes and invalid IEEE-754 values."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class LatencyQuantiles(SimulationDataModel):
    """Latency of completed root transactions only, in milliseconds."""

    p50: float | None = Field(default=None, ge=0.0)
    p95: float | None = Field(default=None, ge=0.0)
    p99: float | None = Field(default=None, ge=0.0)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        """Reject contradictory quantiles when the adjacent values exist."""
        if self.p50 is not None and self.p95 is not None and self.p50 > self.p95:
            message = "p50 must not exceed p95"
            raise ValueError(message)
        if self.p95 is not None and self.p99 is not None and self.p95 > self.p99:
            message = "p95 must not exceed p99"
            raise ValueError(message)
        return self


class NodeSimulationMetrics(SimulationDataModel):
    """Report observed metrics for one node, not for the whole client flow."""

    node_identifier: str = Field(min_length=1)
    utilization_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    mean_queue_length: float | None = Field(default=None, ge=0.0)
    queue_length_time_p95: float | None = Field(default=None, ge=0.0)
    mean_queue_wait_milliseconds: float | None = Field(default=None, ge=0.0)
    rejected_requests: int = Field(default=0, ge=0)


class SimulationExperiment(SimulationDataModel):
    """Aggregate one measurement cohort across independent replications.

    Each measured *root* request ends as completed, rejected, timed out,
    failed or unfinished at the simulation horizon. Child events from
    fan-out cannot increase the generated root-request count.
    """

    workload_id: SimulationWorkload
    offered_requests_per_second: float = Field(gt=0.0)
    generated_requests: int = Field(ge=0)
    completed_requests: int = Field(ge=0)
    rejected_requests: int = Field(ge=0)
    unfinished_requests: int = Field(ge=0)
    timed_out_requests: int = Field(default=0, ge=0)
    failed_requests: int = Field(default=0, ge=0)
    client_latency_milliseconds: LatencyQuantiles = Field(
        default_factory=LatencyQuantiles
    )
    throughput_requests_per_second: float | None = Field(default=None, ge=0.0)
    nodes: list[NodeSimulationMetrics] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_root_request_accounting(self) -> Self:
        """Prevent disappearing client transactions in report aggregates."""
        terminal = (
            self.completed_requests
            + self.rejected_requests
            + self.unfinished_requests
            + self.timed_out_requests
            + self.failed_requests
        )
        if terminal != self.generated_requests:
            message = "root request outcomes must sum to generated_requests"
            raise ValueError(message)
        return self


class ConfidenceInterval(SimulationDataModel):
    """Report confidence bounds for a fraction, rather than for displayed p99."""

    lower: float = Field(ge=0.0, le=1.0)
    upper: float = Field(ge=0.0, le=1.0)
    confidence_level: float = Field(gt=0.0, lt=1.0)
    method: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        """Keep reported uncertainty intervals ordered."""
        if self.lower > self.upper:
            message = "confidence lower bound must not exceed upper bound"
            raise ValueError(message)
        return self


class RequirementEvaluation(SimulationDataModel):
    """Store a non-functional requirement verdict and its actual evidence."""

    requirement_index: int = Field(ge=0)
    type_identifier: RequirementKind
    phase: SimulationWorkload
    threshold_value: float = Field(ge=0.0)
    percentile: float | None = Field(default=None, ge=0.0, le=100.0)
    observed_value: float | None = Field(default=None, ge=0.0)
    status: RequirementVerdict
    confidence_interval: ConfidenceInterval | None = None
    reason_code: SimulationReasonCode | None = None

    @model_validator(mode="after")
    def validate_verdict_evidence(self) -> Self:
        """Require evidence for conclusive results and reasons otherwise."""
        if self.status in (RequirementVerdict.MET, RequirementVerdict.VIOLATED):
            if self.observed_value is None or self.confidence_interval is None:
                message = "conclusive verdict requires observed value and CI"
                raise ValueError(message)
        elif self.reason_code is None:
            message = "non-conclusive verdict requires a reason code"
            raise ValueError(message)
        if (
            self.status is RequirementVerdict.NOT_EVALUATED
            and (
                self.observed_value is not None
                or self.confidence_interval is not None
            )
        ):
            message = "unsupported requirement cannot contain observations"
            raise ValueError(message)
        return self


class SimulationFinding(SimulationDataModel):
    """Report one rule-based observation without recalculating statistics."""

    code: SimulationFindingCode
    severity: Literal["info", "warning", "error"]
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    recommendation: str | None = None
    affected_node_identifiers: list[str] = Field(default_factory=list)


class SimulationLimitation(SimulationDataModel):
    """Disclose a known modeling limitation in structured form."""

    code: SimulationLimitationCode
    description: str = Field(min_length=1)


class SimulationReport(SimulationDataModel):
    """Represent the canonical simulation JSON consumed by later PDF output."""

    schema_version: Literal["1.0"] = "1.0"
    scenario_identifier: str = Field(min_length=1)
    model_version: Literal["simpy-v1"] = "simpy-v1"
    status: SimulationReportStatus
    configuration: SimulationConfiguration = Field(
        default_factory=SimulationConfiguration
    )
    experiments: list[SimulationExperiment] = Field(default_factory=list)
    requirements: list[RequirementEvaluation] = Field(default_factory=list)
    findings: list[SimulationFinding] = Field(default_factory=list)
    limitations: list[SimulationLimitation] = Field(default_factory=list)
