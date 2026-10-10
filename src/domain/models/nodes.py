from pydantic import BaseModel, Field

from domain.models.enums import DatabaseRole, NodeType


class BaseNode(BaseModel):
    identifier: str
    node_type: NodeType
    replicas_count: int = Field(default=1, ge=1)

    maximum_concurrency: int = Field(gt=0)
    maximum_queue_size: int = Field(ge=0)

    mean_processing_time_milliseconds: float = Field(gt=0.0)
    standard_deviation_processing_time: float = Field(ge=0.0)

    monthly_cost_usd: float = Field(ge=0.0)


class DatabaseNode(BaseNode):
    node_type: NodeType = NodeType.DATABASE
    database_role: DatabaseRole = DatabaseRole.PRIMARY
    shards_count: int = Field(default=1, ge=1)
    input_output_operations_per_second_limit: int | None = None


class CacheNode(BaseNode):
    node_type: NodeType = NodeType.CACHE
    cache_hit_rate_probability: float = Field(default=0.8, ge=0.0, le=1.0)
    eviction_policy: str = "least_recently_used"


class MessageBrokerNode(BaseNode):
    node_type: NodeType = NodeType.MESSAGE_BROKER
    maximum_queue_size: int = Field(default=1_000_000)
    retention_period_hours: int | None = None
