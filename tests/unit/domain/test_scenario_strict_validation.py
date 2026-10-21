"""Test strict YAML scenario validation."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from domain.models.scenarios import DesignScenario

pytestmark = pytest.mark.unit



@pytest.mark.parametrize("unknown_field", ["requrements", "worklod"])
def test_rejects_unknown_scenario_keys(unknown_field: str) -> None:
    """Reject misspelled top-level keys instead of dropping them."""
    with pytest.raises(ValidationError) as captured:
        DesignScenario.model_validate(
            {"description": "A valid description", unknown_field: []}
        )

    assert any(
        detail["loc"] == (unknown_field,)
        and detail["type"] == "extra_forbidden"
        for detail in captured.value.errors()
    )


def test_rejects_unknown_workload_keys() -> None:
    """Reject nested workload typos."""
    with pytest.raises(ValidationError) as captured:
        DesignScenario.model_validate(
            {
                "description": "A valid description",
                "workload": {
                    "baseline_requests_per_second": 10.0,
                    "peak_requests_per_second": 20.0,
                    "read_rato": 0.6,
                },
            }
        )

    assert any(
        detail["loc"] == ("workload", "read_rato")
        and detail["type"] == "extra_forbidden"
        for detail in captured.value.errors()
    )


def test_rejects_unknown_requirement_keys() -> None:
    """Reject unknown fields inside requirement objects."""
    with pytest.raises(ValidationError) as captured:
        DesignScenario.model_validate(
            {
                "description": "A valid description",
                "requirements": [
                    {
                        "type_identifier": "budget",
                        "threshold_value": 100.0,
                        "thresold_value": 90.0,
                    }
                ],
            }
        )

    assert any(
        detail["type"] == "extra_forbidden"
        and "thresold_value" in detail["loc"]
        for detail in captured.value.errors()
    )


@pytest.mark.parametrize("name_field", ["identifier", "project_name"])
def test_accepts_both_project_name_spellings(name_field: str) -> None:
    """Keep the documented identifier alias for older YAML scenarios."""
    scenario = DesignScenario.model_validate(
        {name_field: "legacy_project", "description": "Legacy C4-only scenario"}
    )

    assert scenario.identifier == "legacy_project"
    assert scenario.requirements == []
    assert scenario.functional_requirements == []


@pytest.mark.parametrize(
    "scenario_path",
    sorted((Path(__file__).resolve().parents[3] / "scenarios").glob("*.yaml")),
    ids=lambda path: path.name,
)
def test_repository_scenarios_parse_strictly(scenario_path: Path) -> None:
    """Load every bundled YAML file through the strict input model."""
    data = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))

    scenario = DesignScenario.model_validate(data)

    assert scenario.description
