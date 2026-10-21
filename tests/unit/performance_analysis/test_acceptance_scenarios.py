"""Validate manual acceptance inputs without requesting an LLM response."""

from pathlib import Path

import pytest
import yaml

from domain.models.scenarios import DesignScenario

pytestmark = pytest.mark.unit

_SCENARIOS_DIR = Path(__file__).resolve().parents[3] / "scenarios" / "performance"


@pytest.mark.parametrize(
    ("filename", "expected_workload"),
    [
        ("checkout_baseline.yaml", True),
        ("catalog_read_heavy.yaml", True),
        ("notifications_spiky.yaml", True),
        ("helpdesk_no_workload.yaml", False),
    ],
)
def test_manual_acceptance_scenarios_match_contract(
    filename: str,
    expected_workload: bool,
) -> None:
    payload = yaml.safe_load((_SCENARIOS_DIR / filename).read_text(encoding="utf-8"))
    scenario = DesignScenario.model_validate(payload)

    assert scenario.identifier == filename.removesuffix(".yaml")
    assert len(scenario.functional_requirements) >= 2
    assert scenario.requirements
    assert (scenario.workload is not None) is expected_workload
    assert len({item.identifier for item in scenario.functional_requirements}) == len(
        scenario.functional_requirements
    )
    if scenario.workload is not None:
        assert (
            scenario.workload.peak_requests_per_second
            >= scenario.workload.baseline_requests_per_second
        )
