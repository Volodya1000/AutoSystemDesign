"""Serialize verified scenarios and their source evidence."""

import json
from pathlib import Path

from domain.models.scenarios import DesignScenario
from domain.scenario_extraction import DocumentScenarioResult


def write_evidence_manifest(path: Path, result: DocumentScenarioResult) -> None:
    """Persist citations and diagnostics even when no safe scenario can be produced."""
    payload = {
        "source_name": result.source_name,
        "is_relevant": result.is_relevant,
        "field_evidence": result.field_evidence,
        "issues": [issue.model_dump(mode="json") for issue in result.issues],
        "scenario_created": result.scenario is not None,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def scenario_payload(scenario: DesignScenario) -> dict[str, object]:
    """Serialize a scenario while preserving required union discriminators."""
    payload = scenario.model_dump(mode="json", exclude_unset=True, exclude_none=True)
    payload["requirements"] = [
        requirement.model_dump(mode="json", exclude_unset=True, exclude_none=True)
        | {"type_identifier": requirement.type_identifier}
        for requirement in scenario.requirements
    ]
    return payload
