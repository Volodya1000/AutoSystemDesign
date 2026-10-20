from enum import StrEnum


class Operator(StrEnum):
    LESS_THAN = "<"
    LESS_THAN_OR_EQUAL = "<="
    EQUAL = "=="
    GREATER_THAN_OR_EQUAL = ">="
    GREATER_THAN = ">"


class NodeType(StrEnum):
    CLIENT = "client"
    LOAD_BALANCER = "load_balancer"
    COMPUTE = "compute"
    DATABASE = "database"
    CACHE = "cache"
    MESSAGE_BROKER = "message_broker"


class EdgeRoutingMode(StrEnum):
    """Describe how an edge carries requests from its source node."""

    ALTERNATIVE = "alternative"
    FAN_OUT = "fan_out"


class DatabaseRole(StrEnum):
    PRIMARY = "primary"
    REPLICA = "replica"
