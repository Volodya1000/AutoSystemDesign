"""Declare explicit failures of incomplete simulation experiments."""


class SimulationEventLimitExceeded(RuntimeError):
    """Reject an incomplete run rather than presenting partial data as success."""

    def __init__(self, event_limit: int, stopped_at_seconds: float) -> None:
        self.event_limit: int = event_limit
        self.stopped_at_seconds: float = stopped_at_seconds
        message: str = (
            f"Simulation event limit {event_limit} reached "
            f"at virtual time {stopped_at_seconds} s"
        )
        super().__init__(message)
