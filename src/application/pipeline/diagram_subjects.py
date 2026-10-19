"""Typed subjects prepared by pipeline stages for diagram renderers.

A ``DiagramRenderer[SubjectT]`` implementation receives only the subject
and cannot look up auxiliary data on its own.  Some diagram types need
more than their primary domain payload: a sequence diagram, for example,
must know each component's C4 ``NodeType`` to pick the right PlantUML
participant keyword, and the C4 graph is not part of the
``InteractionScenario``.  The subjects below bundle exactly what each
renderer needs, so the port stays unchanged and the stage remains the
single place that knows where the auxiliary data comes from.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.models.sequence import InteractionScenario
    from domain.models.topology import ArchitectureGraph


@dataclass(frozen=True)
class SequenceDiagramSubject:
    """An interaction scenario paired with the C4 graph it references.

    ``architecture_graph`` is required so the renderer can resolve each
    ``ComponentLifeline.architecture_node_id`` to a ``NodeType`` without
    re-querying the scenario or the upstream stage.
    """

    scenario: InteractionScenario
    architecture_graph: ArchitectureGraph
