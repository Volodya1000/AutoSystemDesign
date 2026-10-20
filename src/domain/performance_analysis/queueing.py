"""Shared result contract for queueing-model calculations."""

from enum import StrEnum
from math import isfinite
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QueueingStatus(StrEnum):
    """State whether a steady-state queueing estimate exists."""

    STABLE = "stable"
    UNSTABLE = "unstable"


class QueueingMetrics(BaseModel):
    """Finite metrics from a queueing model.

    An unstable system has no finite steady-state waiting-time estimate, so
    both time fields must be null. Utilization is allowed to exceed one to
    describe offered load beyond service capacity.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    status: QueueingStatus
    utilization_ratio: float = Field(ge=0.0)
    mean_queue_wait_milliseconds: float | None = Field(default=None, ge=0.0)
    mean_response_time_milliseconds: float | None = Field(default=None, ge=0.0)

    @model_validator(mode="after")
    def _validate_status_consistency(self) -> Self:
        has_queue_wait = self.mean_queue_wait_milliseconds is not None
        has_response_time = self.mean_response_time_milliseconds is not None
        if self.status is QueueingStatus.STABLE:
            if self.utilization_ratio >= 1.0 or not (
                has_queue_wait and has_response_time
            ):
                message = (
                    "Stable queueing metrics require utilization below one "
                    "and both finite time estimates."
                )
                raise ValueError(message)
        elif self.utilization_ratio < 1.0 or has_queue_wait or has_response_time:
            message = (
                "Unstable queueing metrics require utilization of at least one "
                "and unavailable time estimates."
            )
            raise ValueError(message)
        return self



def validate_queueing_rates(
    arrival_rate_requests_per_second: float,
    service_rate_requests_per_second: float,
) -> None:
    """Reject rates that cannot describe a physical queueing model."""
    if (
        not isfinite(arrival_rate_requests_per_second)
        or arrival_rate_requests_per_second < 0.0
    ):
        message = "Arrival rate must be finite and non-negative."
        raise ValueError(message)
    if (
        not isfinite(service_rate_requests_per_second)
        or service_rate_requests_per_second <= 0.0
    ):
        message = "Service rate must be finite and positive."
        raise ValueError(message)



def create_stable_queueing_metrics(
    utilization_ratio: float,
    mean_queue_wait_milliseconds: float,
    mean_response_time_milliseconds: float,
) -> QueueingMetrics:
    """Validate finite estimates and build a stable queueing result."""
    if not isfinite(mean_queue_wait_milliseconds) or not isfinite(
        mean_response_time_milliseconds
    ):
        message = "Calculated queueing metrics exceed the finite float range."
        raise ValueError(message)
    return QueueingMetrics(
        status=QueueingStatus.STABLE,
        utilization_ratio=utilization_ratio,
        mean_queue_wait_milliseconds=mean_queue_wait_milliseconds,
        mean_response_time_milliseconds=mean_response_time_milliseconds,
    )
