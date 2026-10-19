import pytest
import yaml

from domain.models.scenarios import DesignScenario

pytestmark = pytest.mark.unit


def test_legacy_yaml_without_functional_requirements_parses_correctly() -> None:
    """Keep legacy C4 scenarios valid after adding sequence features."""
    yaml_text = """
    identifier: legacy_project
    description: Just a plain C4 project
    workload:
      baseline_requests_per_second: 100.0
      peak_requests_per_second: 200.0
    requirements:
      - type_identifier: latency
        threshold_value: 300.0
        percentile: 99.0
    """
    data = yaml.safe_load(yaml_text)
    scenario = DesignScenario.model_validate(data)

    assert scenario.identifier == "legacy_project"
    assert len(scenario.functional_requirements) == 0  # Defaults to empty list safely
