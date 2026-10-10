from pydantic import Field

from domain.models.base_constraints import (
    IntervalRequirement,
    PercentileThresholdRequirement,
    ThresholdRequirement,
)
from domain.models.enums import Operator


class LatencyRequirement(PercentileThresholdRequirement):
    operator: Operator = Operator.LESS_THAN_OR_EQUAL


class QueueSizePercentileRequirement(PercentileThresholdRequirement):
    operator: Operator = Operator.LESS_THAN_OR_EQUAL


class BudgetRequirement(ThresholdRequirement):
    operator: Operator = Operator.LESS_THAN_OR_EQUAL


class AvailabilityRequirement(ThresholdRequirement):
    threshold_value: float = Field(ge=0.0, le=100.0)
    operator: Operator = Operator.GREATER_THAN_OR_EQUAL


class ResourceUtilizationRequirement(IntervalRequirement):
    minimum_value: float = Field(ge=0.0, le=100.0)
    maximum_value: float = Field(ge=0.0, le=100.0)
