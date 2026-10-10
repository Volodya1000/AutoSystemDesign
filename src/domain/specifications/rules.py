from typing import NamedTuple

from domain.models.enums import NodeType


class ConnectionType(NamedTuple):
    """Allowed transition between node types (source -> target)."""

    source: NodeType
    target: NodeType


DEFAULT_ALLOWED_CONNECTION_TYPES: set[ConnectionType] = {
    # Entry points
    ConnectionType(source=NodeType.CLIENT, target=NodeType.LOAD_BALANCER),
    ConnectionType(source=NodeType.CLIENT, target=NodeType.COMPUTE),
    # Traffic distribution
    ConnectionType(source=NodeType.LOAD_BALANCER, target=NodeType.COMPUTE),
    # Application backend communication
    ConnectionType(source=NodeType.COMPUTE, target=NodeType.COMPUTE),
    ConnectionType(source=NodeType.COMPUTE, target=NodeType.DATABASE),
    ConnectionType(source=NodeType.COMPUTE, target=NodeType.CACHE),
    ConnectionType(source=NodeType.COMPUTE, target=NodeType.MESSAGE_BROKER),
    # Asynchronous consumer workers
    ConnectionType(source=NodeType.MESSAGE_BROKER, target=NodeType.COMPUTE),
}
