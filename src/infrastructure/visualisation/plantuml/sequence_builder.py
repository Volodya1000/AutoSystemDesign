from __future__ import annotations

from application.pipeline.diagram_subjects import SequenceDiagramSubject
from domain.models.ast_steps import (
    AltStep,
    LoopStep,
    MessageStep,
    OptStep,
    ScenarioStep,
)
from domain.models.enums import NodeType
from domain.models.sequence import (
    InteractionScenario,
    ScenarioLifeline,
    UserLifeline,
)
from infrastructure.visualisation.plantuml.diagram_registry import (
    register_diagram_builder,
)
from infrastructure.visualisation.plantuml.participant_kinds import (
    participant_keyword,
)
from infrastructure.visualisation.plantuml.ports import DiagramSourceBuilder


@register_diagram_builder("sequence")
def _sequence_builder_factory() -> DiagramSourceBuilder:
    return SequenceDiagramBuilder()


class SequenceDiagramBuilder:
    """Builds the PlantUML source of a sequence diagram.

    Accepts either a ``SequenceDiagramSubject`` (scenario + C4 graph,
    preferred: components get their mapped UML keyword) or a bare
    ``InteractionScenario`` (legacy: every component renders as a plain
    ``participant``).
    """

    def build(
        self,
        subject: SequenceDiagramSubject | InteractionScenario,
        title: str | None = None,
    ) -> str:
        scenario, node_type_by_id = self._unpack(subject)
        lines = ["@startuml", f"title {title or scenario.description}"]
        for lifeline in scenario.lifelines:
            lines.append(self._format_participant(lifeline, node_type_by_id))
        lines.append("")
        lines.extend(self._build_steps(scenario.steps, 0))
        lines.append("@enduml")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _unpack(
        subject: SequenceDiagramSubject | InteractionScenario,
    ) -> tuple[InteractionScenario, dict[str, NodeType]]:
        if isinstance(subject, SequenceDiagramSubject):
            return subject.scenario, {
                node.identifier: node.node_type
                for node in subject.architecture_graph.nodes
            }
        return subject, {}

    @staticmethod
    def _format_participant(
        lifeline: ScenarioLifeline,
        node_type_by_id: dict[str, NodeType],
    ) -> str:
        keyword = participant_keyword(lifeline, node_type_by_id)
        if isinstance(lifeline, UserLifeline):
            return (
                f'{keyword} "{lifeline.scenario_role}\\n'
                f'({lifeline.business_role_id})" '
                f"as {lifeline.lifeline_id}"
            )
        return f'{keyword} "{lifeline.display_name}" as {lifeline.lifeline_id}'

    def _build_steps(self, steps: list[ScenarioStep], indent_level: int) -> list[str]:
        lines = []
        indent = "  " * indent_level
        for step in steps:
            if isinstance(step, MessageStep):
                arrow = "->>" if step.delivery_mode == "async" else "->"
                desc = f" [{step.description}]" if step.description else ""
                lines.append(
                    f"{indent}{step.from_lifeline} {arrow} {step.to_lifeline} "
                    f": {step.action_name}{desc}"
                )
            elif isinstance(step, AltStep):
                for i, branch in enumerate(step.branches):
                    keyword = "alt" if i == 0 else "else"
                    cond = f" {branch.condition}" if branch.condition else ""
                    lines.append(f"{indent}{keyword}{cond}")
                    lines.extend(self._build_steps(branch.steps, indent_level + 1))
                lines.append(f"{indent}end")
            elif isinstance(step, OptStep):
                lines.append(f"{indent}opt {step.condition}")
                lines.extend(self._build_steps(step.steps, indent_level + 1))
                lines.append(f"{indent}end")
            elif isinstance(step, LoopStep):
                lines.append(f"{indent}loop {step.condition}")
                lines.extend(self._build_steps(step.steps, indent_level + 1))
                lines.append(f"{indent}end")
        return lines
