# Copyright (c) 2026 Volodya1000
"""Regression tests for serializing document-extracted scenarios."""

import pytest
import yaml

from domain.models import AvailabilityRequirement, DesignScenario, LatencyRequirement
from scripts.extract_document_scenario import _scenario_payload


def test_scenario_payload_round_trips_discriminated_requirements() -> None:
    scenario = DesignScenario(
        identifier="online_store",
        description="Online store checkout",
        requirements=[
            LatencyRequirement(threshold_value=300.0, percentile=95.0),
            AvailabilityRequirement(threshold_value=99.9),
        ],
    )

    payload = _scenario_payload(scenario)
    restored = DesignScenario.model_validate(yaml.safe_load(yaml.safe_dump(payload)))

    assert [type(requirement) for requirement in restored.requirements] == [
        LatencyRequirement,
        AvailabilityRequirement,
    ]
    assert [requirement.type_identifier for requirement in restored.requirements] == [
        "latency",
        "availability",
    ]
    assert isinstance(restored.requirements[0], LatencyRequirement)
    assert restored.requirements[0].threshold_value == pytest.approx(300.0)
    assert isinstance(restored.requirements[1], AvailabilityRequirement)
    assert restored.requirements[1].threshold_value == pytest.approx(99.9)
