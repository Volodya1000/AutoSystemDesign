# Copyright (c) 2026 Volodya1000
"""Format a design scenario as plain text for logs and prompts."""

from domain.models.scenarios import DesignScenario


def render_scenario_summary(scenario: DesignScenario) -> str:
    """Return a stable human-readable summary of a design scenario."""
    lines: list[str] = [
        f"Scenario: {scenario.identifier}",
        f"Description: {scenario.description}",
    ]
    if scenario.workload is not None:
        lines.extend(
            [
                "Workload:",
                (
                    "- Baseline load: "
                    f"{scenario.workload.baseline_requests_per_second} RPS"
                ),
                f"- Peak load: {scenario.workload.peak_requests_per_second} RPS",
                (
                    f"- Read ratio: {scenario.workload.read_ratio:.2f}, "
                    f"write ratio: {scenario.workload.write_ratio:.2f}"
                ),
            ]
        )
    if scenario.functional_requirements:
        lines.append("Functional requirements:")
        lines.extend(
            f"- [{req.identifier}] {req.name}: {req.text}"
            for req in scenario.functional_requirements
        )
    if scenario.requirements:
        lines.append("Non-functional requirements that the design must satisfy:")
        lines.extend(
            f"- {requirement.model_dump_json()}"
            for requirement in scenario.requirements
        )
    if scenario.allowed_node_types is not None:
        allowed: str = ", ".join(sorted(nt.value for nt in scenario.allowed_node_types))
        lines.append(f"Allowed node types (use ONLY these): {allowed}")
    return "\n".join(lines)
