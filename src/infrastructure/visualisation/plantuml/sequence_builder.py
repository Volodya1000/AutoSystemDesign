from domain.models.ast_steps import (
    AltStep,
    LoopStep,
    MessageStep,
    OptStep,
    ScenarioStep,
)
from domain.models.sequence import InteractionScenario, UserLifeline
from infrastructure.visualisation.plantuml.diagram_registry import (
    register_diagram_builder,
)
from infrastructure.visualisation.plantuml.ports import DiagramSourceBuilder


@register_diagram_builder("sequence")
def _sequence_builder_factory() -> DiagramSourceBuilder:
    return SequenceDiagramBuilder()


class SequenceDiagramBuilder:
    def build(self, scenario: InteractionScenario, title: str | None = None) -> str:
        display_title = title or scenario.description
        lines = ["@startuml", f"title {display_title}"]

        for lifeline in scenario.lifelines:
            if isinstance(lifeline, UserLifeline):
                lines.append(
                    f'actor "{lifeline.scenario_role}\\n'
                    f'({lifeline.business_role_id})" '
                    f"as {lifeline.lifeline_id}"
                )
            else:
                lines.append(
                    f'participant "{lifeline.display_name}" as {lifeline.lifeline_id}'
                )

        lines.append("")
        lines.extend(self._build_steps(scenario.steps, 0))
        lines.append("@enduml")
        return "\n".join(lines) + "\n"

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
