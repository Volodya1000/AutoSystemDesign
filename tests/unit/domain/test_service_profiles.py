"""Verify explicit profiles, provenance and honest unknown latency values."""

import math

import pytest
from pydantic import ValidationError

from application.performance_analysis.report_builder import (
    build_performance_analysis_report,
)
from domain.models.enums import NodeType
from domain.models.nodes import CapacityNode
from domain.models.scenarios import DesignScenario, WorkloadProfile
from domain.models.topology import ArchitectureGraph
from domain.service_profiles import (
    ProfileApplication,
    ServiceProfile,
    ServiceProfileCatalog,
)
from tests.factories import (
    create_test_compute_node,
    create_test_edge,
    create_test_node,
    create_test_service_profile,
)

pytestmark = pytest.mark.unit


def _graph() -> ArchitectureGraph:
    return ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node("orders"),
        ],
        edges=[create_test_edge("client", "orders")],
    )


def _scenario() -> DesignScenario:
    return DesignScenario(
        description="Orders",
        workload=WorkloadProfile(
            baseline_requests_per_second=20, peak_requests_per_second=50, read_ratio=0.8
        ),
    )


def test_profile_supplies_channels_without_mutating_original() -> None:
    original: ArchitectureGraph = _graph()
    catalog: ServiceProfileCatalog = ServiceProfileCatalog(
        by_node_type={NodeType.COMPUTE: create_test_service_profile()}
    )
    result: ProfileApplication = catalog.apply(original)
    assert result.applied["orders"].provenance == "assumption"
    assert isinstance(original.nodes[1], CapacityNode)
    assert original.nodes[1].service_channels_per_replica is None
    report = build_performance_analysis_report(result.graph, _scenario())
    latency: float | None = report.estimated_longest_synchronous_path_mean_milliseconds
    assert latency is not None
    assert math.isfinite(latency)
    assert report.critical_path_node_identifiers == ["client", "orders"]


def test_without_profile_concurrency_does_not_become_service_channels() -> None:
    report = build_performance_analysis_report(_graph(), _scenario())
    assert report.estimated_longest_synchronous_path_mean_milliseconds is None


def test_node_specific_profile_overrides_type_defaults() -> None:
    specific: ServiceProfile = create_test_service_profile().model_copy(
        update={"monthly_cost_usd": 75}
    )
    result: ProfileApplication = ServiceProfileCatalog(
        by_node_type={NodeType.COMPUTE: create_test_service_profile()},
        by_node_id={"orders": specific},
    ).apply(_graph())
    assert result.applied["orders"] == specific
    assert isinstance(result.graph.nodes[1], CapacityNode)
    assert result.graph.nodes[1].monthly_cost_usd == 75


def test_unmapped_node_does_not_block_generation() -> None:
    original: ArchitectureGraph = _graph()
    result: ProfileApplication = ServiceProfileCatalog().apply(original)
    assert result.graph == original
    assert not result.applied


def test_partial_profile_overrides_only_explicit_fields() -> None:
    original: ArchitectureGraph = _graph()
    profile: ServiceProfile = ServiceProfile(
        source="BRD: capacity section",
        provenance="measurement",
        service_channels_per_replica=2,
    )
    result: ProfileApplication = ServiceProfileCatalog(
        by_node_id={"orders": profile}
    ).apply(original)
    assert isinstance(original.nodes[1], CapacityNode)
    assert isinstance(result.graph.nodes[1], CapacityNode)
    assert result.graph.nodes[1].service_channels_per_replica == 2
    assert result.graph.nodes[1].maximum_concurrency == original.nodes[1].maximum_concurrency
    assert result.graph.nodes[1].monthly_cost_usd == original.nodes[1].monthly_cost_usd


@pytest.mark.parametrize(
    "changes",
    [
        {"service_channels_per_replica": 9},
        {"service_channels_per_replica": 0},
        {"mean_processing_time_milliseconds": float("nan")},
        {"source": " "},
        {"unknown": 1},
    ],
)
def test_invalid_profile_is_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ServiceProfile.model_validate(
            create_test_service_profile().model_dump() | changes
        )


def test_client_cannot_have_service_capacity() -> None:
    with pytest.raises(ValidationError):
        ServiceProfileCatalog(
            by_node_type={NodeType.CLIENT: create_test_service_profile()}
        )
