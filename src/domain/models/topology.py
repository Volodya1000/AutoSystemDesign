from pydantic import BaseModel

from domain.models.edges import Edge
from domain.models.nodes import BaseNode, CacheNode, DatabaseNode, MessageBrokerNode

AnyNode = DatabaseNode | CacheNode | MessageBrokerNode | BaseNode


class ArchitectureGraph(BaseModel):
    nodes: list[AnyNode]
    edges: list[Edge]
