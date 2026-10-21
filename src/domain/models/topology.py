# Copyright (c) 2026 Volodya1000
from typing import Annotated

from pydantic import BaseModel, Field

from domain.models.edges import Edge
from domain.models.nodes import (
    CacheNode,
    ClientNode,
    ComputeNode,
    DatabaseNode,
    LoadBalancerNode,
    MessageBrokerNode,
)

# Strict discriminated union: every node payload must resolve to exactly one
# concrete node class; unknown shapes are rejected loudly.
AnyNode = Annotated[
    ClientNode
    | LoadBalancerNode
    | ComputeNode
    | DatabaseNode
    | CacheNode
    | MessageBrokerNode,
    Field(discriminator="node_type"),
]


class ArchitectureGraph(BaseModel):
    nodes: list[AnyNode]
    edges: list[Edge]
