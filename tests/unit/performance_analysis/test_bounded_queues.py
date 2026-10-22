"""Finite-queue tests: unsupported blocking must not become invented metrics."""

import pytest

from application.performance_analysis.report_builder import (
    build_performance_analysis_report,
)
from domain.models.enums import NodeType
from domain.models.scenarios import DesignScenario, WorkloadProfile
from domain.models.topology import ArchitectureGraph
from domain.performance_analysis.report import PerformanceAnalysisStatus
from tests.factories import (
    create_test_compute_node,
    create_test_edge,
    create_test_latency_graph,
    create_test_node,
)

pytestmark = pytest.mark.unit


def _scenario() -> DesignScenario:
    return DesignScenario(
        identifier="bounded_queue",
        description="Finite buffer acceptance",
        workload=WorkloadProfile(
            baseline_requests_per_second=10.0,
            peak_requests_per_second=20.0,
        ),
    )


@pytest.mark.parametrize(
    ("queue_size", "expected_wait"),
    [
        (0, None),
        (5, 2.5),
    ],
)
def test_active_finite_queue_omits_unsupported_loss_notices(
    queue_size: int,
    expected_wait: float | None,
) -> None:
    graph = create_test_latency_graph(
        service_channels_per_replica=1,
        queue_size=queue_size,
    )

    report = build_performance_analysis_report(graph, _scenario())
    service = next(item for item in report.nodes if item.node_identifier == "service")
    assert report.findings == []
    assert report.status is PerformanceAnalysisStatus.PARTIAL
    if expected_wait is None:
        assert service.estimated_mean_queue_wait_milliseconds is None
        assert service.estimated_mean_response_time_milliseconds is None
        assert report.estimated_longest_synchronous_path_mean_milliseconds is None
    else:
        # Explicit infinite-waiting-room proxy, NOT a finite-buffer prediction.
        assert service.estimated_mean_queue_wait_milliseconds == pytest.approx(
            expected_wait
        )
        assert service.estimated_mean_response_time_milliseconds == pytest.approx(
            expected_wait + 10.0
        )


def test_disconnected_zero_buffer_keeps_only_calculated_metrics() -> None:
    graph = ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node(
                "active",
                queue_size=5,
                service_channels_per_replica=1,
            ),
            create_test_compute_node(
                "idle",
                queue_size=0,
                service_channels_per_replica=1,
            ),
        ],
        edges=[create_test_edge("client", "active")],
    )

    report = build_performance_analysis_report(graph, _scenario())
    idle = next(item for item in report.nodes if item.node_identifier == "idle")
    assert idle.incoming_requests_per_second == pytest.approx(0.0)
    assert idle.estimated_mean_queue_wait_milliseconds == pytest.approx(0.0)
    assert report.findings == []
