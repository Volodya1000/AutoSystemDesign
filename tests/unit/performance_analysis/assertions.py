"""Shared assertions for queueing result contracts."""

import json

from domain.performance_analysis.queueing import QueueingMetrics, QueueingStatus


def assert_unstable_queueing_metrics(result: QueueingMetrics) -> None:
    """Assert the public contract for a queue without a finite steady state."""
    assert result.status is QueueingStatus.UNSTABLE
    assert result.mean_queue_wait_milliseconds is None
    assert result.mean_response_time_milliseconds is None

    serialized: dict[str, object] = json.loads(result.model_dump_json())
    assert serialized["mean_queue_wait_milliseconds"] is None
    assert serialized["mean_response_time_milliseconds"] is None
