from pydantic import BaseModel, ConfigDict, Field

from domain.models.enums import EdgeRoutingMode
from domain.models.protocols import ConnectionProtocol


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_identifier: str
    target_identifier: str
    protocol: ConnectionProtocol
    routing_mode: EdgeRoutingMode = Field(
        default=EdgeRoutingMode.ALTERNATIVE,
        description=(
            "Alternative edges split source traffic equally; fan_out edges each "
            "receive the full traffic rate."
        ),
    )
    description: str = Field(
        default="",
        description=(
            "Semantic description: purpose, payload, request nature "
            "and expected response"
        ),
    )

    network_latency_milliseconds: float = Field(default=2.0, ge=0.0)
    retry_attempts_count: int = Field(default=0, ge=0)
    timeout_milliseconds: float = Field(default=5000.0, gt=0.0)
