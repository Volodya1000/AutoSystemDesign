from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from domain.models.enums import DatabaseRole, NodeType


class BaseNode(BaseModel):
    """Abstract base carrying identity fields shared by every topology node."""

    model_config = ConfigDict(extra="forbid")

    identifier: str
    node_type: NodeType
    replicas_count: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _reject_direct_base_instantiation(self) -> "BaseNode":
        if self.__class__ is BaseNode:  # pylint: disable=unidiomatic-typecheck
            raise ValueError(
                "BaseNode is abstract: instantiate a concrete node subclass"
            )
        return self


class CapacityNode(BaseNode):
    """Abstract base for nodes with processing capacity, queueing and cost."""

    maximum_concurrency: int = Field(gt=0)
    maximum_queue_size: int = Field(ge=0)

    mean_processing_time_milliseconds: float = Field(gt=0.0)
    standard_deviation_processing_time: float = Field(ge=0.0)

    monthly_cost_usd: float = Field(ge=0.0)

    @model_validator(mode="after")
    def _reject_direct_capacity_instantiation(self) -> "CapacityNode":
        if self.__class__ is CapacityNode:  # pylint: disable=unidiomatic-typecheck
            raise ValueError(
                "CapacityNode is abstract: instantiate a concrete node subclass"
            )
        return self


class ClientNode(BaseNode):
    """External traffic source: has no capacity, queue or cost attributes."""

    node_type: Literal[NodeType.CLIENT] = NodeType.CLIENT


class LoadBalancerNode(CapacityNode):
    node_type: Literal[NodeType.LOAD_BALANCER] = NodeType.LOAD_BALANCER


class ComputeNode(CapacityNode):
    node_type: Literal[NodeType.COMPUTE] = NodeType.COMPUTE


class DatabaseNode(CapacityNode):
    node_type: Literal[NodeType.DATABASE] = NodeType.DATABASE
    database_role: DatabaseRole = DatabaseRole.PRIMARY
    shards_count: int = Field(default=1, ge=1)
    input_output_operations_per_second_limit: int | None = None


class CacheNode(CapacityNode):
    node_type: Literal[NodeType.CACHE] = NodeType.CACHE
    cache_hit_rate_probability: float = Field(default=0.8, ge=0.0, le=1.0)
    eviction_policy: str = "least_recently_used"


class MessageBrokerNode(CapacityNode):
    node_type: Literal[NodeType.MESSAGE_BROKER] = NodeType.MESSAGE_BROKER
    maximum_queue_size: int = Field(default=1_000_000, ge=0)
    retention_period_hours: int | None = None
