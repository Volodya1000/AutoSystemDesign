import math
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from domain.exceptions.model_validation_errors import (
    ModelValidationCode,
    ModelValidationError,
)
from domain.models.enums import Operator


class BaseRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Признак необходимого входного профиля, не поле YAML/JSON сценария.
    # Расширения задают его в конкретном типе требования.
    requires_workload: ClassVar[bool] = False

    def is_met_requirement(self, actual_value: float) -> bool:
        raise NotImplementedError()


class ThresholdRequirement(BaseRequirement):
    threshold_value: float
    operator: Operator

    def is_met_requirement(self, actual_value: float) -> bool:
        match self.operator:
            case Operator.LESS_THAN:
                return actual_value < self.threshold_value
            case Operator.LESS_THAN_OR_EQUAL:
                return actual_value <= self.threshold_value
            case Operator.EQUAL:
                # Exact float equality is brittle; compare approximately instead.
                return math.isclose(actual_value, self.threshold_value)
            case Operator.GREATER_THAN_OR_EQUAL:
                return actual_value >= self.threshold_value
            case Operator.GREATER_THAN:
                return actual_value > self.threshold_value
            case _:
                return False


class IntervalRequirement(BaseRequirement):
    minimum_value: float
    maximum_value: float

    @model_validator(mode="after")
    def _validate_interval_bounds(self) -> "IntervalRequirement":
        if self.minimum_value > self.maximum_value:
            raise ModelValidationError(ModelValidationCode.INVALID_INTERVAL_BOUNDS)
        return self

    def is_met_requirement(self, actual_value: float) -> bool:
        return self.minimum_value <= actual_value <= self.maximum_value


class PercentileThresholdRequirement(ThresholdRequirement):
    percentile: float = Field(default=99.0, ge=0.0, le=100.0)
