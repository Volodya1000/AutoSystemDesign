"""Define the structured result contract for performance analysis."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class PerformanceAnalysisStatus(StrEnum):
    """Describe coverage of the analysis, not generation or pipeline execution."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class PerformanceFindingSeverity(StrEnum):
    """Classify the importance of a performance finding."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class PerformanceFindingCode(StrEnum):
    """Identify a finding's meaning independently of its display text."""

    CAPACITY_HEADROOM = "capacity_headroom"
    CAPACITY_SATURATION = "capacity_saturation"
    WORKLOAD_MISSING = "workload_missing"
    METRIC_UNAVAILABLE = "metric_unavailable"
    UNSUPPORTED_MODEL = "unsupported_model"
    LATENCY_NOT_EVALUATED = "latency_not_evaluated"


class NodePerformanceMetrics(BaseModel):
    """Represent calculated performance metrics for one architecture node.

    Optional metrics remain null when they cannot be calculated. They are not
    replaced with zero, because zero is a meaningful measurement. Units and
    metric-specific bounds are encoded in the field names and constraints.
    Utilization may exceed 1.0 when offered load exceeds estimated capacity.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    node_identifier: str = Field(min_length=1)
    incoming_requests_per_second: float | None = Field(default=None, ge=0.0)
    estimated_capacity_requests_per_second: float | None = Field(
        default=None, gt=0.0
    )
    utilization_ratio: float | None = Field(default=None, ge=0.0)
    estimated_mean_queue_wait_milliseconds: float | None = Field(
        default=None, ge=0.0
    )
    estimated_mean_response_time_milliseconds: float | None = Field(
        default=None, ge=0.0
    )


class PerformanceFinding(BaseModel):
    """Describe an issue, risk, or observation found during performance analysis."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    finding_code: PerformanceFindingCode
    severity: PerformanceFindingSeverity
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    affected_node_identifiers: list[str] = Field(default_factory=list)
    recommendation: str | None = None


class PerformanceAnalysisReport(BaseModel):
    """Collect the machine-readable performance analysis result for a scenario.

    Keep only fields that have an agreed meaning and an identified producer.
    Assumptions and schema versioning can be added when their contracts and
    compatibility requirements are defined.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    scenario_identifier: str = Field(min_length=1)
    status: PerformanceAnalysisStatus
    nodes: list[NodePerformanceMetrics] = Field(default_factory=list)
    findings: list[PerformanceFinding] = Field(default_factory=list)
