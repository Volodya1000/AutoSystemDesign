"""Shared fixtures for all tests."""

import pytest

from domain.models import (
    BudgetRequirement,
    DesignScenario,
    LatencyRequirement,
    WorkloadProfile,
)


@pytest.fixture
def scenario() -> DesignScenario:
    """Typed scenario reused by prompt, agent, service and integration tests."""
    return DesignScenario(
        identifier="ecommerce_checkout",
        description="Checkout flow for a mid-size e-commerce platform",
        workload=WorkloadProfile(
            baseline_requests_per_second=120.0,
            peak_requests_per_second=400.0,
            read_ratio=0.7,
        ),
        requirements=[
            LatencyRequirement(threshold_value=300.0, percentile=99.0),
            BudgetRequirement(threshold_value=3000.0),
        ],
    )
