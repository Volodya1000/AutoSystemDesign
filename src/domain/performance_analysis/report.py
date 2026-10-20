"""Define the structured result contract for performance analysis."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PerformanceAnalysisStatus(StrEnum):
    """Describe whether the analysis produced a complete usable result."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class PerformanceFindingSeverity(StrEnum):
    """Classify the importance of a performance finding."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class NodePerformanceMetrics(BaseModel):
    """Represent calculated performance metrics for one architecture node.

    Optional metrics remain null when they cannot be calculated. They are not
    replaced with zero, because zero is a meaningful measurement.
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

    code: str = Field(min_length=1)
    severity: PerformanceFindingSeverity
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    affected_node_identifiers: list[str] = Field(default_factory=list)
    recommendation: str | None = None


class PerformanceAnalysisReport(BaseModel):
    """Collect the machine-readable performance analysis result for a scenario."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    schema_version: Literal["1.0"] = "1.0"
    scenario_identifier: str = Field(min_length=1)
    status: PerformanceAnalysisStatus
    nodes: list[NodePerformanceMetrics] = Field(default_factory=list)
    findings: list[PerformanceFinding] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
