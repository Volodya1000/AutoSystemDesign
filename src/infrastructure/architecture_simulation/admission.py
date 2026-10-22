"""Implement bounded per-replica admission without borrowing C4 concurrency as capacity."""

import simpy

from domain.architecture_simulation.graph_execution import GraphRejectionReason
from domain.architecture_simulation.graph_plan import SimulatedResource


def rejection_reason(
    replica: simpy.Resource, node: SimulatedResource
) -> GraphRejectionReason | None:
    """Decide admission from active channels and the independent queue limit."""
    running: int = len(replica.users)
    waiting: int = len(replica.queue)
    if running + waiting >= node.maximum_concurrency_per_replica:
        return GraphRejectionReason.CONCURRENCY_LIMIT
    if running >= replica.capacity and waiting >= node.maximum_queue_size_per_replica:
        return GraphRejectionReason.QUEUE_FULL
    return None
