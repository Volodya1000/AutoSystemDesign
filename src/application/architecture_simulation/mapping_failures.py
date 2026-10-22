"""Stable reasons for mapping failures."""

from enum import StrEnum


class MappingFailure(StrEnum):
    """Categorize unsupported or inconsistent input without fragile messages."""

    MISSING_WORKLOAD = "missing_workload"
    INVALID_CLIENT_COUNT = "invalid_client_count"
    DUPLICATE_NODE = "duplicate_node"
    UNKNOWN_ENDPOINT = "unknown_endpoint"
    DUPLICATE_EDGE = "duplicate_edge"
    UNSUPPORTED_ASYNC = "unsupported_async"
    UNSUPPORTED_RETRY = "unsupported_retry"
    UNSUPPORTED_BROKER = "unsupported_broker"
    SERVICE_CHANNELS_UNKNOWN = "service_channels_unknown"
    CYCLE = "cycle"
    DISCONNECTED = "disconnected"
