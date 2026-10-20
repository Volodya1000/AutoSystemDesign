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
    """Stable machine-readable categories for performance findings.

    CAPACITY_HEADROOM means that estimated demand is below estimated capacity,
    leaving spare capacity (запас пропускной способности).

    CAPACITY_SATURATION means that estimated demand is at or near the capacity
    limit defined by the applicable validation rule (насыщение пропускной
    способности). It does not necessarily mean demand is mathematically
    greater than capacity; the validator may warn before that point.

    These codes identify the kind of finding, not its severity or its display
    text. Keep them stable for JSON/API consumers.
    """

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
    estimated_capacity_requests_per_second: float | None = Field(default=None, gt=0.0)
    utilization_ratio: float | None = Field(default=None, ge=0.0)
    estimated_mean_queue_wait_milliseconds: float | None = Field(default=None, ge=0.0)
    estimated_mean_response_time_milliseconds: float | None = Field(
        default=None, ge=0.0
    )


class PerformanceFinding(BaseModel):
    """Describe an issue, risk, or observation found during performance analysis.

    The report builder should populate title and description from deterministic
    templates selected by finding_code and the calculated metrics. The initial
    implementation must not ask an LLM to invent findings or recommendations:
    deterministic output is testable and reproducible.

    Recommendation is optional and should be supplied only when a supported
    rule provides a justified action. If no reliable action can be inferred,
    leave it as None rather than suggesting a guess.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    finding_code: PerformanceFindingCode = Field(
        description="Stable machine-readable category; not an HTTP status code."
    )
    severity: PerformanceFindingSeverity = Field(
        description="Importance of this finding: informational, warning, or error."
    )
    title: str = Field(
        min_length=1,
        description="Short human-readable title from a deterministic message template.",
    )
    description: str = Field(
        min_length=1,
        description="Explanation based on calculated values and known model limits.",
    )
    affected_node_identifiers: list[str] = Field(
        default_factory=list,
        description="Identifiers of architecture nodes related to this finding.",
    )
    recommendation: str | None = Field(
        default=None,
        description="Optional rule-based next step; null when no action is justified.",
    )


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
