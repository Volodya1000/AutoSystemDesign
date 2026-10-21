# Copyright (c) 2026 Volodya1000
from pydantic import BaseModel, Field

from domain.models.enums import NodeType


class NodeProfile(BaseModel):
    identifier: str
    node_type: NodeType

    maximum_concurrency: int = Field(gt=0)
    maximum_queue_size: int = Field(ge=0)

    mean_processing_time_milliseconds: float = Field(gt=0.0)
    standard_deviation_processing_time: float = Field(ge=0.0)

    monthly_cost_usd: float = Field(ge=0.0)


class ProfileRegistry(BaseModel):
    profiles: dict[str, NodeProfile] = Field(default_factory=dict)

    def register_profile(self, profile: NodeProfile) -> None:
        self.profiles[profile.identifier] = profile

    def get_profile(self, identifier: str) -> NodeProfile | None:
        return self.profiles.get(identifier)
