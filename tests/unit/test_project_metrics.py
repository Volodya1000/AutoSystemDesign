"""Tests for truthful project-level latency labels."""

import pytest

from domain.specifications.metrics import ProjectMetrics, format_metrics_title

pytestmark = pytest.mark.unit


def test_metrics_title_labels_latency_as_mean_without_percentile_comparison() -> None:
    title = format_metrics_title(
        ProjectMetrics(
            max_utilization_ratio=0.5,
            critical_path_latency_ms=123.0,
            total_monthly_cost_usd=20.0,
            budget_limit_usd=100.0,
        )
    )

    assert "Path mean 123 ms" in title
    latency_segment = title.split("Path mean", maxsplit=1)[1].split("|", maxsplit=1)[0]
    assert "/" not in latency_segment
