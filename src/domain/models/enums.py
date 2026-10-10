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


class DatabaseRole(StrEnum):
    PRIMARY = "primary"
    REPLICA = "replica"
