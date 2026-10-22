"""Define client-traversal observations for the linear-graph prototype."""

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from domain.architecture_simulation.graph_plan import GraphSimulationPlan


class GraphExecutionModel(BaseModel):
    """Reject unrecognized and non-finite simulation inputs."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class GraphRequestTrace(GraphExecutionModel):
    """Schedule incoming root requests against one mapped C4 graph."""

    plan: GraphSimulationPlan
    arrival_times_seconds: list[Annotated[float, Field(ge=0)]] = Field(
        default_factory=list
    )
    seed: int = Field(ge=0)


class GraphTraversalObservation(GraphExecutionModel):
    """Measure the forward path only, not an invented round-trip response."""

    request_index: int = Field(ge=0)
    arrival_seconds: float = Field(ge=0)
    completion_seconds: float = Field(ge=0)
    visited_resources: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_completion(self) -> Self:
        """Reject a completion recorded before its root request arrived."""
        if self.completion_seconds < self.arrival_seconds:
            message = "completion must not precede arrival"
            raise ValueError(message)
        return self

    @property
    def traversal_seconds(self) -> float:
        """Return one-way modeled processing and network duration."""
        return self.completion_seconds - self.arrival_seconds


class GraphRejectionReason(StrEnum):
    """Identify the actual limit that prevented one replica's admission."""

    CONCURRENCY_LIMIT = "concurrency_limit"
    QUEUE_FULL = "queue_full"


class GraphRequestRejection(GraphExecutionModel):
    """Record one rejected client transaction and its downstream cause."""

    request_index: int = Field(ge=0)
    node_identifier: str = Field(min_length=1)
    replica_index: int = Field(ge=0)
    at_seconds: float = Field(ge=0)
    reason_code: GraphRejectionReason


class GraphTraceWindowResult(GraphExecutionModel):
    """Track complete, rejected and censored requests without hidden losses."""

    observations: list[GraphTraversalObservation] = Field(default_factory=list)
    rejections: list[GraphRequestRejection] = Field(default_factory=list)
    measured_arrivals: int = Field(ge=0)
    unfinished: int = Field(ge=0)
    warmup_arrivals: int = Field(ge=0)
    queue_model: Literal["bounded_per_replica"] = "bounded_per_replica"

    @model_validator(mode="after")
    def validate_accounting(self) -> Self:
        """Preserve every measured arrival across the stopping horizon."""
        counted: int = len(self.observations) + len(self.rejections) + self.unfinished
        if counted != self.measured_arrivals:
            message = "root arrivals must equal completed plus rejected plus unfinished"
            raise ValueError(message)
        return self
