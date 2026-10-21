from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from domain.exceptions.model_validation_errors import (
    ModelValidationCode,
    ModelValidationError,
)
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
            raise ModelValidationError(ModelValidationCode.ABSTRACT_BASE_NODE)
        return self


class CapacityNode(BaseNode):
    """Abstract base for nodes with processing capacity, queueing and cost."""

    maximum_concurrency: int = Field(
        gt=0,
        description=(
            "Maximum concurrent in-flight requests per replica. Capacity uses "
            "this as a proxy only when service_channels_per_replica is "
            "unknown; a concurrency limit is not a queueing server count."
        ),
    )
    maximum_queue_size: int = Field(ge=0)
    service_channels_per_replica: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Optional number of independent service channels per replica. "
            "Leave unset when unknown; do not infer it from maximum_concurrency."
        ),
    )

    mean_processing_time_milliseconds: float = Field(gt=0.0)
    standard_deviation_processing_time: float = Field(ge=0.0)

    monthly_cost_usd: float = Field(ge=0.0)

    @property
    def queueing_server_count(self) -> int | None:
        """Return the total independent queueing channels when explicitly known."""
        if self.service_channels_per_replica is None:
            return None
        return self.replicas_count * self.service_channels_per_replica

    @model_validator(mode="after")
    def _reject_direct_capacity_instantiation(self) -> "CapacityNode":
        if self.__class__ is CapacityNode:  # pylint: disable=unidiomatic-typecheck
            raise ModelValidationError(ModelValidationCode.ABSTRACT_CAPACITY_NODE)
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
