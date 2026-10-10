from pydantic import BaseModel, Field, model_validator

from domain.models.enums import NodeType
from domain.models.requirements import Requirement


class WorkloadProfile(BaseModel):
    baseline_requests_per_second: float = Field(gt=0.0)
    peak_requests_per_second: float = Field(gt=0.0)
    read_ratio: float = Field(default=0.8, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_peak_covers_baseline(self) -> "WorkloadProfile":
        if self.peak_requests_per_second < self.baseline_requests_per_second:
            raise ValueError(
                "peak_requests_per_second must be greater than or equal to "
                "baseline_requests_per_second"
            )
        return self

    @property
    def write_ratio(self) -> float:
        return 1.0 - self.read_ratio


class DesignScenario(BaseModel):
    identifier: str
    description: str

    workload: WorkloadProfile
    requirements: list[Requirement]

    allowed_node_types: set[NodeType] | None = None
