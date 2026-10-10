from pydantic import BaseModel, Field

from domain.models.base_constraints import BaseRequirement
from domain.models.enums import NodeType


class WorkloadProfile(BaseModel):
    baseline_requests_per_second: float = Field(gt=0.0)
    peak_requests_per_second: float = Field(gt=0.0)
    read_ratio: float = Field(default=0.8, ge=0.0, le=1.0)

    @property
    def write_ratio(self) -> float:
        return 1.0 - self.read_ratio


class DesignScenario(BaseModel):
    identifier: str
    description: str

    workload: WorkloadProfile
    requirements: list[BaseRequirement]

    allowed_node_types: set[NodeType] | None = None
