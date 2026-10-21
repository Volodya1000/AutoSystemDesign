# Copyright (c) 2026 Volodya1000
"""Unit tests for sequence generation stage orchestration and artifacts."""

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from application.pipeline.context import StageContext
from application.pipeline.diagram_subjects import SequenceDiagramSubject
from application.pipeline.outcome import DiagramRenderResult, StageOutcome, StageStatus
from application.pipeline.stages.sequence import SequenceStage
from application.results import (
    GenerationAttempt,
    SequenceGenerationResult,
    SequenceScenarioResult,
)
from application.usage import TokenUsage
from domain.models.ast_steps import MessageStep
from domain.models.functional import FunctionalRequirement
from domain.models.roles import BusinessRole, ProjectRolesCatalog
from domain.models.scenarios import DesignScenario
from domain.models.sequence import (
    ComponentLifeline,
    InteractionScenario,
    UserLifeline,
)
from domain.models.topology import ArchitectureGraph
from domain.specifications.interfaces import ValidationResult
from tests.unit.in_memory_writer import InMemoryWriter

pytestmark = pytest.mark.unit


class NullReporter:
    def __init__(self) -> None:
        self.labels: list[str] = []

    def attempts[PayloadT](
        self, attempts: Sequence[GenerationAttempt[PayloadT]], label: str
    ) -> None:
        del attempts
        self.labels.append(label)

    def tokens(self, usage: TokenUsage, generation_seconds: float) -> None:
        assert usage.total_tokens >= 0
        assert generation_seconds >= 0.0


class FakeSequenceGenerator:
    def __init__(self, result: SequenceGenerationResult) -> None:
        self.result = result
        self.calls = 0

    def generate(
        self, scenario: DesignScenario, graph: ArchitectureGraph
    ) -> SequenceGenerationResult:
        del scenario, graph
        self.calls += 1
        return self.result


class FakeSequenceRenderer:
    def __init__(self, result: DiagramRenderResult) -> None:
        self.result = result
        self.calls = 0

    def render(
        self,
        subject: SequenceDiagramSubject,
        *,
        title: str,
        base_name: str,
        out_dir: Path,
    ) -> DiagramRenderResult:
        assert subject.scenario.requirement_identifier == "FR-1"
        assert title == "Interaction for FR-1"
        assert base_name == "sequence_stage_test_seq_fr_1"
        assert out_dir.name == "output"
        self.calls += 1
        return self.result


def _scenario() -> DesignScenario:
    return DesignScenario(
        identifier="sequence_stage_test",
        description="Sequence stage test",
        functional_requirements=[
            FunctionalRequirement(
                identifier="FR-1",
                name="Create resource",
                text="The user creates a resource.",
            )
        ],
    )


def _graph() -> ArchitectureGraph:
    return ArchitectureGraph(nodes=[], edges=[])


def _catalog() -> ProjectRolesCatalog:
    return ProjectRolesCatalog(
        roles=[
            BusinessRole(
                role_id="buyer",
                name="Buyer",
                description="The user initiating the operation.",
            )
        ]
    )


def _interaction() -> InteractionScenario:
    return InteractionScenario(
        scenario_id="FR-1_scenario",
        requirement_identifier="FR-1",
        description="Interaction for FR-1",
        lifelines=[
            UserLifeline(
                kind="user",
                lifeline_id="buyer_1",
                business_role_id="buyer",
                scenario_role="initiator",
                description="The buyer initiating the request.",
            ),
            ComponentLifeline(
                kind="component",
                lifeline_id="api_1",
                architecture_node_id="api",
                display_name="API",
                description="Handles the request.",
            ),
        ],
        steps=[
            MessageStep(
                kind="message",
                from_lifeline="buyer_1",
                to_lifeline="api_1",
                action_name="POST /resources",
                message_kind="user_action",
                delivery_mode="sync",
            )
        ],
    )


def _successful_result() -> SequenceGenerationResult:
    catalog = _catalog()
    interaction = _interaction()
    return SequenceGenerationResult(
        roles_attempts=[
            GenerationAttempt[ProjectRolesCatalog](
                attempt_number=1,
                parsed=True,
                payload=catalog,
                validation=ValidationResult(),
                usage=TokenUsage(prompt_tokens=5, completion_tokens=5),
            )
        ],
        roles_catalog=catalog,
        scenarios_results={
            "FR-1": SequenceScenarioResult(
                attempts=[
                    GenerationAttempt[InteractionScenario](
                        attempt_number=1,
                        parsed=True,
                        payload=interaction,
                        validation=ValidationResult(),
                        usage=TokenUsage(prompt_tokens=10, completion_tokens=10),
                    )
                ],
                interaction_scenario=interaction,
            )
        },
    )


def _failed_result() -> SequenceGenerationResult:
    return SequenceGenerationResult(
        roles_attempts=[],
        roles_catalog=None,
        scenarios_results={
            "FR-1": SequenceScenarioResult(
                attempts=[],
                interaction_scenario=None,
            )
        },
    )


def _context(tmp_path: Path, writer: InMemoryWriter) -> StageContext:
    upstream: Mapping[str, StageOutcome[object]] = {
        "c4": StageOutcome[object](
            name="c4",
            status=StageStatus.SUCCEEDED,
            duration_seconds=0.0,
            total_tokens=0,
            payload=_graph(),
        )
    }
    return StageContext(
        scenario=_scenario(),
        out_dir=tmp_path / "output",
        writer=writer,
        upstream=upstream,
    )


def test_sequence_stage_persists_catalog_ast_and_rendered_diagram(
    tmp_path: Path,
) -> None:
    writer = InMemoryWriter()
    generator = FakeSequenceGenerator(_successful_result())
    renderer = FakeSequenceRenderer(
        DiagramRenderResult(artifacts=(tmp_path / "output" / "sequence.svg",))
    )
    reporter = NullReporter()
    stage = SequenceStage(generator, renderer, reporter)

    outcome = stage.run(_context(tmp_path, writer))

    assert outcome.status is StageStatus.SUCCEEDED
    assert outcome.payload is not None
    assert list(outcome.payload) == ["FR-1"]
    assert generator.calls == 1
    assert renderer.calls == 1
    assert reporter.labels == [
        "Roles catalog attempts",
        "Interaction attempts for FR-1",
    ]
    assert [path.name for path, _ in writer.writes] == [
        "sequence_stage_test_roles.json",
        "sequence_stage_test_seq_fr_1_ast.json",
    ]
    assert [path.name for path in outcome.artifacts] == [
        "sequence_stage_test_roles.json",
        "sequence_stage_test_seq_fr_1_ast.json",
        "sequence.svg",
    ]


def test_sequence_stage_returns_partial_when_diagram_rendering_warns(
    tmp_path: Path,
) -> None:
    writer = InMemoryWriter()
    renderer = FakeSequenceRenderer(
        DiagramRenderResult(warnings=("diagram renderer unavailable",))
    )
    stage = SequenceStage(
        FakeSequenceGenerator(_successful_result()),
        renderer,
        NullReporter(),
    )

    outcome = stage.run(_context(tmp_path, writer))

    assert outcome.status is StageStatus.PARTIAL
    assert outcome.warnings == ("diagram renderer unavailable",)
    assert outcome.payload is not None
    assert len(writer.writes) == 2


def test_sequence_stage_fails_when_required_scenarios_cannot_be_generated(
    tmp_path: Path,
) -> None:
    writer = InMemoryWriter()
    renderer = FakeSequenceRenderer(DiagramRenderResult())
    stage = SequenceStage(
        FakeSequenceGenerator(_failed_result()),
        renderer,
        NullReporter(),
    )

    outcome = stage.run(_context(tmp_path, writer))

    assert outcome.status is StageStatus.FAILED
    assert outcome.payload == {}
    assert renderer.calls == 0
