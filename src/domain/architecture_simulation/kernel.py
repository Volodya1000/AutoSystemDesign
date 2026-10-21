"""Define deterministic single-node service schedules and observations.

All times use seconds of virtual time. The input is deliberately independent
from SimPy so the engine can be replaced without changing domain contracts.
"""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SimulationKernelModel(BaseModel):
    """Validate data crossing the simulation engine boundary."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ScheduledRequest(SimulationKernelModel):
    """Declare when one root request arrives and how long it needs service."""

    arrival_seconds: float = Field(ge=0.0)
    service_seconds: float = Field(gt=0.0)


class SingleNodeSimulationPlan(SimulationKernelModel):
    """Run a deterministic trace through identical parallel service channels.

    No client graph routing, queue limit, randomness or simulation horizon is
    implied by this minimal contract. All scheduled requests drain to completion.
    """

    service_channels: int = Field(ge=1)
    requests: list[ScheduledRequest] = Field(default_factory=list)


class CompletedRequestObservation(SimulationKernelModel):
    """Preserve each request's original index and measured virtual times."""

    request_index: int = Field(ge=0)
    arrival_seconds: float = Field(ge=0.0)
    service_start_seconds: float = Field(ge=0.0)
    completion_seconds: float = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_event_order(self) -> Self:
        """Reject an observation that travels backwards in virtual time."""
        if not (
            self.arrival_seconds
            <= self.service_start_seconds
            <= self.completion_seconds
        ):
            message = "simulation event times must be nondecreasing"
            raise ValueError(message)
        return self

    @property
    def wait_seconds(self) -> float:
        """Return elapsed time between arrival and start of service."""
        return self.service_start_seconds - self.arrival_seconds

    @property
    def response_seconds(self) -> float:
        """Return complete service time including queueing."""
        return self.completion_seconds - self.arrival_seconds


class SingleNodeSimulationResult(SimulationKernelModel):
    """Collect completed observations in original input order."""

    observations: list[CompletedRequestObservation] = Field(default_factory=list)
