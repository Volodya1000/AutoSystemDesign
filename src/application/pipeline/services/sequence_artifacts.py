"""Persistence and rendering of generated sequence artifacts."""

from dataclasses import dataclass
from pathlib import Path

from application.pipeline.context import StageContext
from application.pipeline.diagram_subjects import SequenceDiagramSubject
from application.pipeline.outcome import DiagramRenderResult
from application.pipeline.ports import DiagramRenderer
from domain.models.roles import ProjectRolesCatalog
from domain.models.sequence import InteractionScenario
from domain.models.topology import ArchitectureGraph


@dataclass(frozen=True, slots=True)
class SequenceArtifactResult:
    """Artifacts produced for one interaction plus best-effort render warnings."""

    artifacts: tuple[Path, ...]
    warnings: tuple[str, ...] = ()


class SequenceArtifactProcessor:
    """Persist sequence models and optionally render their diagrams.

    Generation and repair behavior stays in the generation service, while
    the stage remains responsible for orchestration and outcome aggregation.
    """

    def __init__(
        self,
        renderer: DiagramRenderer[SequenceDiagramSubject] | None,
    ) -> None:
        self._renderer: DiagramRenderer[SequenceDiagramSubject] | None = renderer

    @staticmethod
    def persist_roles_catalog(
        context: StageContext,
        catalog: ProjectRolesCatalog | None,
    ) -> tuple[Path, ...]:
        """Persist the roles catalog when generation produced one."""
        if catalog is None:
            return ()

        path: Path = context.writer.write_text(
            context.out_dir / f"{context.scenario.identifier}_roles.json",
            catalog.model_dump_json(indent=2),
        )
        return (path,)

    def persist_interaction(
        self,
        context: StageContext,
        *,
        base_name: str,
        interaction: InteractionScenario,
        graph: ArchitectureGraph,
    ) -> SequenceArtifactResult:
        """Persist the interaction AST and render a diagram when configured."""
        ast_path: Path = context.writer.write_text(
            context.out_dir / f"{base_name}_ast.json",
            interaction.model_dump_json(indent=2),
        )
        artifacts: list[Path] = [ast_path]
        warnings: tuple[str, ...] = ()

        if self._renderer is not None:
            render_result: DiagramRenderResult = self._renderer.render(
                SequenceDiagramSubject(
                    scenario=interaction,
                    architecture_graph=graph,
                ),
                title=interaction.description,
                base_name=base_name,
                out_dir=context.out_dir,
            )
            artifacts.extend(render_result.artifacts)
            warnings = render_result.warnings

        return SequenceArtifactResult(
            artifacts=tuple(artifacts),
            warnings=warnings,
        )
