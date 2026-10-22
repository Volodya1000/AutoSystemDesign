"""Describe unsupported execution semantics using stable typed reasons."""

from enum import StrEnum


class GraphExecutionFailure(StrEnum):
    """Identify graph behavior not yet implemented by the linear prototype."""

    BRANCHING_UNSUPPORTED = "branching_unsupported"
    CACHE_UNSUPPORTED = "cache_unsupported"
    UNKNOWN_RESOURCE = "unknown_resource"
    EVENT_BUDGET_EXCEEDED = "event_budget_exceeded"


class GraphExecutionError(ValueError):
    """Expose why a mapped graph cannot yet be simulated end to end."""

    def __init__(self, code: GraphExecutionFailure, identifier: str) -> None:
        self.code: GraphExecutionFailure = code
        self.identifier: str = identifier
        super().__init__(f"{code.value}: {identifier}")
