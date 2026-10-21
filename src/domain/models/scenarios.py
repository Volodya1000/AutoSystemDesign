from pydantic import BaseModel, ConfigDict, Field, model_validator

from domain.exceptions.model_validation_errors import (
    ModelValidationCode,
    ModelValidationError,
)
from domain.models.enums import NodeType
from domain.models.functional import FunctionalRequirement
from domain.models.requirements import Requirement


class WorkloadProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_requests_per_second: float = Field(gt=0)
    peak_requests_per_second: float = Field(gt=0)
    read_ratio: float = Field(default=0.8, ge=0, le=1.0)

    @model_validator(mode="after")
    def _validate_peak_covers_baseline(self) -> "WorkloadProfile":
        if self.peak_requests_per_second < self.baseline_requests_per_second:
            raise ModelValidationError(ModelValidationCode.WORKLOAD_PEAK_BELOW_BASELINE)
        return self

    @property
    def write_ratio(self) -> float:
        return 1.0 - self.read_ratio


class DesignScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: str = Field(
        default="project",
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
    )
    description: str

    workload: WorkloadProfile | None = None
    requirements: list[Requirement] = Field(default_factory=list)
    functional_requirements: list[FunctionalRequirement] = Field(default_factory=list)

    allowed_node_types: set[NodeType] | None = None
