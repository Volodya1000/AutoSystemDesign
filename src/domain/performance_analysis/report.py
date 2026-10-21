"""Define the structured result contract for performance analysis."""

from enum import StrEnum
from typing import Literal

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
    BOUNDED_QUEUE_UNMODELED = "bounded_queue_unmodeled"


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
    """Represent one finding in the serialized performance report.

    This model intentionally contains both stable machine-readable fields
    (finding_code, severity, affected nodes) and human-readable report fields
    (title, description, recommendation). They are not calculations or a second
    source of metrics: they are two parts of the same JSON report contract.

    The application-layer report builder owns the text. It should select a
    deterministic title template by finding_code and compose the description
    from calculated values and known model limitations. Recommendations must
    come from explicit, supported rules; leave recommendation as None when no
    reliable action is justified. Do not use an LLM to invent these messages.

    Keep this as one serialized finding for KISS. Introduce a separate internal
    diagnostic model and presentation DTO only if a real need appears, such as
    multiple locales or distinct output formats with different text structures.
    A PDF renderer should consume this report rather than recalculate or rewrite
    the finding independently.
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
    The schema_version field is a stable literal contract version; older
    reports without that field remain compatible with the v1 model.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    scenario_identifier: str = Field(min_length=1)
    schema_version: Literal["1.0"] = Field(
        default="1.0",
        description=(
            "Version of the published performance JSON contract. "
            "Legacy payloads without this field are interpreted as 1.0."
        ),
    )
    status: PerformanceAnalysisStatus
    nodes: list[NodePerformanceMetrics] = Field(default_factory=list)
    findings: list[PerformanceFinding] = Field(default_factory=list)
    estimated_longest_synchronous_path_mean_milliseconds: float | None = Field(
        default=None,
        ge=0.0,
        description=(
            "Maximum of per-path mean estimates over synchronous client paths. "
            "Not the mean completion time of a parallel fan-out request."
        ),
    )
    critical_path_node_identifiers: list[str] = Field(
        default_factory=list,
        description="Node identifiers of the path producing the maximum mean.",
    )
