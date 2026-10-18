"""Validation tests for identifiers used in generated artifact paths."""

import pytest
from pydantic import ValidationError

from domain.models.scenarios import DesignScenario

pytestmark = pytest.mark.unit


def _scenario(identifier: str) -> DesignScenario:
    return DesignScenario.model_validate(
        {
            "identifier": identifier,
            "description": "Artifact identifier validation",
        }
    )


@pytest.mark.parametrize(
    "identifier",
    [
        "../outside",
        "nested/name",
        r"nested\\name",
        "/absolute",
        ".hidden",
        "",
        "contains spaces",
    ],
)
def test_scenario_identifier_rejects_unsafe_artifact_names(identifier: str) -> None:
    with pytest.raises(ValidationError):
        _scenario(identifier)


@pytest.mark.parametrize(
    "identifier", ["project", "social_network_chat", "feature-123"]
)
def test_scenario_identifier_accepts_safe_artifact_names(identifier: str) -> None:
    assert _scenario(identifier).identifier == identifier
