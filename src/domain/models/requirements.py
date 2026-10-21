# Copyright (c) 2026 Volodya1000
from typing import Annotated, Literal

from pydantic import Field

from domain.models.base_constraints import (
    IntervalRequirement,
    PercentileThresholdRequirement,
    ThresholdRequirement,
)
from domain.models.enums import Operator


class LatencyRequirement(PercentileThresholdRequirement):
    type_identifier: Literal["latency"] = "latency"
    operator: Operator = Operator.LESS_THAN_OR_EQUAL


class QueueSizePercentileRequirement(PercentileThresholdRequirement):
    type_identifier: Literal["queue_size_percentile"] = "queue_size_percentile"
    operator: Operator = Operator.LESS_THAN_OR_EQUAL


class BudgetRequirement(ThresholdRequirement):
    type_identifier: Literal["budget"] = "budget"
    operator: Operator = Operator.LESS_THAN_OR_EQUAL


class AvailabilityRequirement(ThresholdRequirement):
    type_identifier: Literal["availability"] = "availability"
    threshold_value: float = Field(ge=0.0, le=100.0)
    operator: Operator = Operator.GREATER_THAN_OR_EQUAL


class ResourceUtilizationRequirement(IntervalRequirement):
    type_identifier: Literal["resource_utilization"] = "resource_utilization"
    minimum_value: float = Field(ge=0.0, le=100.0)
    maximum_value: float = Field(ge=0.0, le=100.0)


# Discriminated union: external payloads must declare an explicit requirement
# kind, otherwise unknown fields would be silently discarded by the base class.
Requirement = Annotated[
    LatencyRequirement
    | QueueSizePercentileRequirement
    | BudgetRequirement
    | AvailabilityRequirement
    | ResourceUtilizationRequirement,
    Field(discriminator="type_identifier"),
]
