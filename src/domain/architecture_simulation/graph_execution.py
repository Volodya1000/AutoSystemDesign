"""Define client-traversal observations for the linear-graph prototype."""

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


class GraphTraceWindowResult(GraphExecutionModel):
    """Keep censored root requests visible and disclose unbounded queues."""

    observations: list[GraphTraversalObservation] = Field(default_factory=list)
    measured_arrivals: int = Field(ge=0)
    unfinished: int = Field(ge=0)
    warmup_arrivals: int = Field(ge=0)
    queue_model: Literal["unbounded_prototype"] = "unbounded_prototype"

    @model_validator(mode="after")
    def validate_accounting(self) -> Self:
        """Preserve every measured arrival across the stopping horizon."""
        if len(self.observations) + self.unfinished != self.measured_arrivals:
            message = "root arrivals must equal completed plus unfinished"
            raise ValueError(message)
        return self
