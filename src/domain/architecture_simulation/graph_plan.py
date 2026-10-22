"""Define validated, deterministic input contracts for C4 simulation mapping."""

from pydantic import BaseModel, ConfigDict, Field

from domain.models.enums import EdgeRoutingMode, NodeType


class SimulationGraphModel(BaseModel):
    """Reject unmodelled properties and non-finite physical values."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class SimulatedResource(SimulationGraphModel):
    """Preserve per-replica limits without inventing service channels."""

    identifier: str = Field(min_length=1)
    node_type: NodeType
    replicas_count: int = Field(ge=1)
    service_channels_per_replica: int = Field(ge=1)
    maximum_concurrency_per_replica: int = Field(ge=1)
    maximum_queue_size_per_replica: int = Field(ge=0)
    mean_service_seconds: float = Field(gt=0)
    std_service_seconds: float = Field(ge=0)
    cache_hit_probability: float | None = Field(default=None, ge=0, le=1)


class SimulatedConnection(SimulationGraphModel):
    """Retain routing and connection constraints for the future graph engine."""

    source_identifier: str
    target_identifier: str
    routing_mode: EdgeRoutingMode
    network_latency_seconds: float = Field(ge=0)
    timeout_seconds: float = Field(gt=0)


class GraphSimulationPlan(SimulationGraphModel):
    """Store a sorted DAG and the real baseline/peak workload inputs."""

    scenario_identifier: str = Field(min_length=1)
    client_identifier: str = Field(min_length=1)
    baseline_requests_per_second: float = Field(gt=0)
    peak_requests_per_second: float = Field(gt=0)
    resources: list[SimulatedResource] = Field(min_length=1)
    connections: list[SimulatedConnection] = Field(min_length=1)
    topological_order: list[str] = Field(min_length=2)
