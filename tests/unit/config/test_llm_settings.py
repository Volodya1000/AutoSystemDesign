"""Unit tests of LlmSettings validation rules."""

from typing import Any

import pytest
from pydantic import ValidationError

from config.llm import LlmSettings, StructuredOutputMode

pytestmark = pytest.mark.unit

_VALID_KWARGS: dict[str, Any] = {
    "model": "lm_studio/qwen3-8b",
    "temperature": 0.2,
    "max_tokens": 2048,
    "timeout_seconds": 180.0,
    "structured_output_mode": StructuredOutputMode.PROMPT,
}


class TestLlmSettings:
    def test_all_fields_are_required(self) -> None:
        with pytest.raises(ValidationError):
            LlmSettings()  # type: ignore[call-arg]  # deliberately invalid

    def test_accepts_valid_values(self) -> None:
        settings: LlmSettings = LlmSettings(**_VALID_KWARGS)
        assert settings.model == "lm_studio/qwen3-8b"
        assert settings.temperature == EXPECTED_ASSERT_SETTINGS_TEMPERATURE
        assert settings.structured_output_mode is StructuredOutputMode.PROMPT

    def test_rejects_temperature_out_of_bounds(self) -> None:
        with pytest.raises(ValidationError):
            LlmSettings(**{**_VALID_KWARGS, "temperature": 5.0})

    def test_rejects_non_positive_max_tokens(self) -> None:
        with pytest.raises(ValidationError):
            LlmSettings(**{**_VALID_KWARGS, "max_tokens": 0})

EXPECTED_ASSERT_SETTINGS_TEMPERATURE = 0.2

