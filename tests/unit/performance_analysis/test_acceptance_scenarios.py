"""Validate manual acceptance inputs without requesting an LLM response."""

from pathlib import Path

import pytest
import yaml

from domain.models.scenarios import DesignScenario

pytestmark = pytest.mark.unit

_SCENARIOS_DIR = Path(__file__).resolve().parents[3] / "scenarios" / "performance"


@pytest.mark.parametrize(
    ("filename", "workload_state"),
    [
        ("checkout_baseline.yaml", "present"),
        ("catalog_read_heavy.yaml", "present"),
        ("notifications_spiky.yaml", "present"),
        ("helpdesk_no_workload.yaml", "absent"),
    ],
)
def test_manual_acceptance_scenarios_match_contract(
    filename: str,
    workload_state: str,
) -> None:
    payload = yaml.safe_load((_SCENARIOS_DIR / filename).read_text(encoding="utf-8"))
    scenario = DesignScenario.model_validate(payload)

    assert scenario.identifier == filename.removesuffix(".yaml")
    assert len(scenario.functional_requirements) >= 2
    assert scenario.requirements
    assert (scenario.workload is not None) is (workload_state == "present")
    assert len({item.identifier for item in scenario.functional_requirements}) == len(
        scenario.functional_requirements
    )
    if scenario.workload is not None:
        assert (
            scenario.workload.peak_requests_per_second
            >= scenario.workload.baseline_requests_per_second
        )
