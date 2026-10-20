"""Unit tests for sequence artifact persistence and rendering."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from application.pipeline.context import StageContext
from application.pipeline.diagram_subjects import SequenceDiagramSubject
from application.pipeline.outcome import DiagramRenderResult, StageOutcome
from application.pipeline.sequence_artifacts import SequenceArtifactProcessor
from application.pipeline.stage import StageId
from domain.models.ast_steps import MessageStep
from domain.models.roles import BusinessRole, ProjectRolesCatalog
from domain.models.scenarios import DesignScenario
from domain.models.sequence import ComponentLifeline, InteractionScenario, UserLifeline
from domain.models.topology import ArchitectureGraph
from tests.unit.in_memory_writer import InMemoryWriter

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

pytestmark = pytest.mark.unit


class FakeRenderer:
    def __init__(self, result: DiagramRenderResult) -> None:
        self.result: DiagramRenderResult = result
        self.calls: int = 0
        self.received_subject: SequenceDiagramSubject | None = None

    def render(
        self,
        subject: SequenceDiagramSubject,
        *,
        title: str,
        base_name: str,
        out_dir: Path,
    ) -> DiagramRenderResult:
        assert title == "Create a resource"
        assert base_name == "demo_seq_fr_1"
        assert out_dir.name == "output"
        self.calls += 1
        self.received_subject = subject
        return self.result


def _context(tmp_path: Path, writer: InMemoryWriter) -> StageContext:
    upstream: Mapping[StageId, StageOutcome[object]] = {}
    return StageContext(
        scenario=DesignScenario(identifier="demo", description="Test scenario"),
        out_dir=tmp_path / "output",
        writer=writer,
        upstream=upstream,
    )


def _catalog() -> ProjectRolesCatalog:
    return ProjectRolesCatalog(
        roles=[
            BusinessRole(
                role_id="buyer",
                name="Buyer",
                description="User who initiates the request.",
            )
        ]
    )


def _interaction() -> InteractionScenario:
    return InteractionScenario(
        scenario_id="FR-1_scenario",
        requirement_identifier="FR-1",
        description="Create a resource",
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


def test_persist_roles_catalog_is_a_noop_for_missing_catalog(tmp_path: Path) -> None:
    writer = InMemoryWriter()
    context = _context(tmp_path, writer)

    paths = SequenceArtifactProcessor.persist_roles_catalog(context, None)

    assert not paths
    assert not writer.writes


def test_persist_roles_catalog_writes_json_to_scenario_output(tmp_path: Path) -> None:
    writer = InMemoryWriter()
    context = _context(tmp_path, writer)
    catalog = _catalog()

    paths = SequenceArtifactProcessor.persist_roles_catalog(context, catalog)

    assert paths == (tmp_path / "output" / "demo_roles.json",)
    assert writer.writes == [
        (
            tmp_path / "output" / "demo_roles.json",
            catalog.model_dump_json(indent=2),
        )
    ]


def test_persist_interaction_writes_ast_without_renderer(tmp_path: Path) -> None:
    writer = InMemoryWriter()
    context = _context(tmp_path, writer)
    interaction = _interaction()
    processor = SequenceArtifactProcessor(renderer=None)

    result = processor.persist_interaction(
        context,
        base_name="demo_seq_fr_1",
        interaction=interaction,
        graph=ArchitectureGraph(nodes=[], edges=[]),
    )

    assert result.artifacts == (tmp_path / "output" / "demo_seq_fr_1_ast.json",)
    assert not result.warnings
    assert writer.writes[0] == (
        tmp_path / "output" / "demo_seq_fr_1_ast.json",
        interaction.model_dump_json(indent=2),
    )


def test_persist_interaction_aggregates_rendered_artifacts_and_warnings(
    tmp_path: Path,
) -> None:
    writer = InMemoryWriter()
    context = _context(tmp_path, writer)
    graph = ArchitectureGraph(nodes=[], edges=[])
    interaction = _interaction()
    rendered_path = tmp_path / "output" / "demo_seq_fr_1.svg"
    renderer = FakeRenderer(
        DiagramRenderResult(
            artifacts=(rendered_path,),
            warnings=("renderer unavailable for one format",),
        )
    )
    processor = SequenceArtifactProcessor(renderer=renderer)

    result = processor.persist_interaction(
        context,
        base_name="demo_seq_fr_1",
        interaction=interaction,
        graph=graph,
    )

    assert result.artifacts == (
        tmp_path / "output" / "demo_seq_fr_1_ast.json",
        rendered_path,
    )
    assert result.warnings == ("renderer unavailable for one format",)
    assert renderer.calls == 1
    assert renderer.received_subject == SequenceDiagramSubject(
        scenario=interaction,
        architecture_graph=graph,
    )
