"""Provide a deterministic offline C4 stage for demonstrations and tests.

This adapter substitutes only the external architecture generation boundary.
Downstream stages receive the real typed architecture and write real artifacts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.pipeline.outcome import StageOutcome, StageStatus
from application.pipeline.stage import StageId
from domain.models.topology import ArchitectureGraph

if TYPE_CHECKING:
    from pathlib import Path

    from application.pipeline.context import StageContext


class OfflineC4Stage:
    """Supply a validated fixture graph instead of contacting the LLM."""

    name: StageId = StageId.C4
    depends_on: tuple[StageId, ...] = ()

    def __init__(self, graph: ArchitectureGraph) -> None:
        self._graph: ArchitectureGraph = graph

    def run(self, context: StageContext) -> StageOutcome[object]:
        """Persist the graph and make it available to actual downstream stages."""
        graph_path: Path = context.writer.write_text(
            context.out_dir / "architecture_graph.json",
            self._graph.model_dump_json(indent=2),
        )
        return StageOutcome[object](
            name=self.name,
            status=StageStatus.SUCCEEDED,
            duration_seconds=0.0,
            total_tokens=0,
            artifacts=(graph_path,),
            payload=self._graph,
        )
