"""Regression tests for mean latency and percentile-SLO semantics."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from application.performance_analysis.report_builder import (
    build_performance_analysis_report,
)
from application.results import GenerationStatus
from application.tasks import DesignProposal, DesignTask
from application.usage import TokenUsage
from config.llm import LlmSettings, StructuredOutputMode
from config.root import AppSettings
from domain.models.enums import NodeType
from domain.models.requirements import LatencyRequirement
from domain.models.scenarios import DesignScenario, WorkloadProfile
from domain.models.topology import ArchitectureGraph
from domain.performance_analysis.report import (
    PerformanceAnalysisStatus,
    PerformanceFindingCode,
)
from infrastructure import composition
from tests.factories import create_test_compute_node, create_test_edge, create_test_node

pytestmark = pytest.mark.unit


def _scenario() -> DesignScenario:
    return DesignScenario(
        identifier="latency_slo_test",
        description="A percentile target that the current model cannot evaluate",
        workload=WorkloadProfile(
            baseline_requests_per_second=10.0,
            peak_requests_per_second=20.0,
        ),
        requirements=[LatencyRequirement(threshold_value=1.0, percentile=99.0)],
    )


def _graph() -> ArchitectureGraph:
    return ArchitectureGraph(
        nodes=[
            create_test_node("client", NodeType.CLIENT),
            create_test_compute_node(
                "service",
                concurrency=1,
                mean_ms=10.0,
                std_ms=10.0,
            ),
        ],
        edges=[create_test_edge("client", "service")],
    )


def test_percentile_target_is_not_evaluated_but_mean_estimate_remains_available() -> None:
    report = build_performance_analysis_report(_graph(), _scenario())

    service_metrics = next(
        metrics for metrics in report.nodes if metrics.node_identifier == "service"
    )
    findings = [
        finding
        for finding in report.findings
        if finding.finding_code is PerformanceFindingCode.LATENCY_NOT_EVALUATED
    ]

    assert report.status is PerformanceAnalysisStatus.PARTIAL
    assert service_metrics.estimated_mean_response_time_milliseconds is not None
    assert service_metrics.estimated_mean_response_time_milliseconds > 1.0
    assert len(findings) == 1
    assert findings[0].affected_node_identifiers


class _FakeLlmClient:
    def __init__(self, settings: AppSettings) -> None:
        del settings


class _FixedArchitectureDesigner:
    def __init__(self, graph: ArchitectureGraph) -> None:
        self._graph = graph
        self.calls = 0

    def propose(self, task: DesignTask) -> DesignProposal:
        del task
        self.calls += 1
        return DesignProposal(
            graph=self._graph,
            raw_content="{}",
            usage=TokenUsage(),
        )


def _settings() -> AppSettings:
    return AppSettings(
        base_url="http://localhost:1234/v1",
        api_key=SecretStr("fake"),
        llm=LlmSettings(
            model="lm_studio/fake",
            temperature=0.0,
            max_tokens=64,
            timeout_seconds=5.0,
            structured_output_mode=StructuredOutputMode.PROMPT,
        ),
    )


def test_unmodelled_percentile_target_does_not_trigger_repair_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    designer = _FixedArchitectureDesigner(_graph())

    def build_fixed_designer(
        client: _FakeLlmClient,
        settings: AppSettings,
    ) -> _FixedArchitectureDesigner:
        del client, settings
        return designer

    monkeypatch.setattr(composition, "LiteLlmClient", _FakeLlmClient)
    monkeypatch.setattr(composition, "ArchitectureDesignerAgent", build_fixed_designer)

    service = composition.build_design_generation_service(settings=_settings())
    result = service.generate(_scenario())

    assert result.status is GenerationStatus.SUCCEEDED
    assert len(result.attempts) == 1
    assert designer.calls == 1
