"""Regression tests for legacy scenarios that have no functional requirements."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from types import MappingProxyType

import pytest
import yaml

from application.pipeline.context import StageContext
from application.pipeline.outcome import StageOutcome, StageStatus
from application.pipeline.stages.api import ApiStage
from application.pipeline.stages.sequence import SequenceStage
from application.results import (
    ApiGenerationResult,
    GenerationAttempt,
    SequenceGenerationResult,
)
from application.usage import TokenUsage
from domain.models import DesignScenario
from domain.models.sequence import InteractionScenario
from domain.models.topology import ArchitectureGraph

pytestmark = pytest.mark.unit

LEGACY_SCENARIO_YAML = """
project_name: legacy_project
description: A legacy C4 scenario without functional requirements
workload:
  baseline_requests_per_second: 100.0
  peak_requests_per_second: 200.0
requirements:
  - type_identifier: latency
    threshold_value: 300.0
    percentile: 99.0
"""


class InMemoryWriter:
    def __init__(self) -> None:
        self.writes: list[tuple[Path, str]] = []

    def write_text(self, path: Path, content: str) -> Path:
        self.writes.append((path, content))
        return path


class NullGenerationReporter:
    def attempts(self, attempts: Sequence[GenerationAttempt], label: str) -> None:
        del attempts, label

    def tokens(self, usage: TokenUsage, generation_seconds: float) -> None:
        del usage, generation_seconds


class CountingSequenceGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def generate(
        self, scenario: DesignScenario, graph: ArchitectureGraph
    ) -> SequenceGenerationResult:
        del scenario, graph
        self.calls += 1
        return SequenceGenerationResult()


class CountingApiGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def generate(
        self,
        scenario: DesignScenario,
        graph: ArchitectureGraph,
        sequences: dict[str, InteractionScenario],
    ) -> ApiGenerationResult:
        del scenario, graph, sequences
        self.calls += 1
        return ApiGenerationResult()


def _legacy_scenario() -> DesignScenario:
    return DesignScenario.model_validate(yaml.safe_load(LEGACY_SCENARIO_YAML))


def _upstream(graph: ArchitectureGraph) -> dict[str, StageOutcome[object]]:
    return {
        "c4": StageOutcome(
            name="c4",
            status=StageStatus.SUCCEEDED,
            duration_seconds=0.0,
            total_tokens=0,
            payload=graph,
        ),
        "sequence": StageOutcome(
            name="sequence",
            status=StageStatus.SUCCEEDED,
            duration_seconds=0.0,
            total_tokens=0,
            payload={},
        ),
    }


def test_legacy_yaml_without_functional_requirements_still_parses() -> None:
    scenario = _legacy_scenario()

    assert scenario.identifier == "legacy_project"
    assert scenario.functional_requirements == []


def test_sequence_stage_skips_generation_without_functional_requirements(
    tmp_path: Path,
) -> None:
    scenario = _legacy_scenario()
    graph = ArchitectureGraph(nodes=[], edges=[])
    service = CountingSequenceGenerator()
    stage = SequenceStage(service, renderer=None, reporter=NullGenerationReporter())
    context = StageContext(
        scenario=scenario,
        out_dir=tmp_path,
        writer=InMemoryWriter(),
        upstream=MappingProxyType({"c4": _upstream(graph)["c4"]}),
    )

    outcome = stage.run(context)

    assert service.calls == 0
    assert outcome.status is StageStatus.SUCCEEDED
    assert outcome.payload == {}
    assert not outcome.artifacts


def test_api_stage_skips_generation_without_functional_requirements(
    tmp_path: Path,
) -> None:
    scenario = _legacy_scenario()
    graph = ArchitectureGraph(nodes=[], edges=[])
    service = CountingApiGenerator()
    stage = ApiStage(service, renderer=None, reporter=NullGenerationReporter())
    context = StageContext(
        scenario=scenario,
        out_dir=tmp_path,
        writer=InMemoryWriter(),
        upstream=MappingProxyType(_upstream(graph)),
    )

    outcome = stage.run(context)

    assert service.calls == 0
    assert outcome.status is StageStatus.SUCCEEDED
    assert outcome.payload is None
    assert not outcome.artifacts
