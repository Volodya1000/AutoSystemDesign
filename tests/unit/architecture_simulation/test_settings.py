"""Check that simulation configuration is integrated into Pydantic Settings."""

import pytest
from pydantic import ValidationError

from config.llm import LlmSettings, StructuredOutputMode
from config.root import AppSettings
from domain.architecture_simulation.configuration import SimulationConfiguration

pytestmark = pytest.mark.unit


def _app_settings() -> AppSettings:
    return AppSettings(
        base_url="http://localhost:1234/v1",
        api_key="test",
        llm=LlmSettings(
            model="lm_studio/example",
            temperature=0.3,
            max_tokens=128,
            timeout_seconds=10.0,
            structured_output_mode=StructuredOutputMode.JSON_OBJECT,
        ),
    )


def test_defaults_are_available_without_a_simulation_yaml_section() -> None:
    settings = _app_settings()

    assert settings.simulation == SimulationConfiguration()


def test_simulation_settings_can_be_overridden_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASD_SIMULATION__REPLICATIONS", "7")
    monkeypatch.setenv("ASD_SIMULATION__BASE_SEED", "0")

    settings = _app_settings()

    assert settings.simulation.replications == 7
    assert settings.simulation.base_seed == 0


def test_simulation_settings_reject_an_unknown_parameter() -> None:
    with pytest.raises(ValidationError):
        SimulationConfiguration.model_validate({"unknown": 5})


def test_settings_reject_invalid_replication_count() -> None:
    with pytest.raises(ValidationError):
        SimulationConfiguration(replications=0)


def test_settings_reject_non_finite_duration() -> None:
    with pytest.raises(ValidationError):
        SimulationConfiguration(measurement_seconds=float("nan"))
