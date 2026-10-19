"""Regression tests for legacy scenarios that have no functional requirements."""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING

import pytest
import yaml

from application.pipeline.context import StageContext
from application.pipeline.outcome import StageOutcome, StageStatus
from application.pipeline.runner import PipelineRunner
from application.pipeline.stages.api import ApiStage
from application.pipeline.stages.c4 import C4Stage
from application.pipeline.stages.sequence import SequenceStage
from application.results import (
    ApiGenerationResult,
    DesignGenerationResult,
    GenerationAttempt,
    SequenceGenerationResult,
)
from application.usage import TokenUsage
from domain.models import DesignScenario
from domain.models.functional import FunctionalRequirement
from domain.models.topology import ArchitectureGraph
from domain.specifications.interfaces import ValidationResult
from tests.unit.in_memory_writer import InMemoryWriter

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from domain.models.sequence import InteractionScenario

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
        sequences: Mapping[str, InteractionScenario],
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


class SuccessfulDesignGenerator:
    def generate(self, scenario: DesignScenario) -> DesignGenerationResult:
        del scenario
        graph = ArchitectureGraph(nodes=[], edges=[])
        return DesignGenerationResult(
            attempts=[
                GenerationAttempt[ArchitectureGraph](
                    attempt_number=1,
                    parsed=True,
                    payload=graph,
                    validation=ValidationResult(),
                    usage=TokenUsage(),
                )
            ]
        )


class CapturingPipelineReporter:
    def __init__(self) -> None:
        self.reports: list[list[StageOutcome[object]]] = []

    def report(self, outcomes: Sequence[StageOutcome[object]]) -> None:
        self.reports.append(list(outcomes))


def _scenario_with_functional_requirement() -> DesignScenario:
    scenario = _legacy_scenario()
    return scenario.model_copy(
        update={
            "functional_requirements": [
                FunctionalRequirement(
                    identifier="FR-1",
                    name="Create resource",
                    text="The user creates a resource.",
                )
            ]
        }
    )


def test_legacy_pipeline_skips_sequence_and_api_but_keeps_c4_successful(
    tmp_path: Path,
) -> None:
    scenario = _legacy_scenario()
    writer = InMemoryWriter()
    generation_reporter = NullGenerationReporter()
    sequence_service = CountingSequenceGenerator()
    api_service = CountingApiGenerator()
    pipeline_reporter = CapturingPipelineReporter()
    runner = PipelineRunner(
        stages=[
            C4Stage(
                SuccessfulDesignGenerator(),
                renderer=None,
                reporter=generation_reporter,
            ),
            SequenceStage(
                sequence_service,
                renderer=None,
                reporter=generation_reporter,
            ),
            ApiStage(
                api_service,
                renderer=None,
                reporter=generation_reporter,
            ),
        ],
        reporter=pipeline_reporter,
    )

    exit_code = runner.run(scenario, tmp_path, writer)

    assert exit_code == 0
    outcomes = pipeline_reporter.reports[-1]
    assert [(outcome.name, outcome.status) for outcome in outcomes] == [
        ("c4", StageStatus.SUCCEEDED),
        ("sequence", StageStatus.SUCCEEDED),
        ("api", StageStatus.SUCCEEDED),
    ]
    assert outcomes[1].payload == {}
    assert outcomes[2].payload is None
    assert sequence_service.calls == 0
    assert api_service.calls == 0
    assert [path.name for path, _ in writer.writes] == ["legacy_project_c4.json"]


def test_sequence_generation_failure_still_fails_for_functional_scenarios(
    tmp_path: Path,
) -> None:
    scenario = _scenario_with_functional_requirement()
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

    assert service.calls == 1
    assert outcome.status is StageStatus.FAILED


def test_api_generation_failure_still_fails_for_functional_scenarios(
    tmp_path: Path,
) -> None:
    scenario = _scenario_with_functional_requirement()
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

    assert service.calls == 1
    assert outcome.status is StageStatus.FAILED
