# Copyright (c) 2026 Volodya1000
"""Unit tests for validated LLM settings overrides."""

import pytest
from pydantic import ValidationError

from config.llm import StructuredOutputMode
from config.root import AppSettings, with_llm_updates
from tests.llm_support import make_settings

pytestmark = pytest.mark.unit


class TestWithLlmUpdates:
    @staticmethod
    def test_valid_overrides_keep_other_fields_and_original_unchanged() -> None:
        settings: AppSettings = make_settings()

        updated: AppSettings = with_llm_updates(
            settings,
            temperature=0.7,
            max_tokens=512,
            context_window_tokens=4096,
            structured_output_mode="prompt",
        )

        assert updated is not settings
        assert updated.llm is not settings.llm
        assert updated.llm.temperature == pytest.approx(0.7)
        assert updated.llm.max_tokens == 512
        assert updated.llm.context_window_tokens == 4096
        assert updated.llm.structured_output_mode is StructuredOutputMode.PROMPT
        assert updated.llm.model == settings.llm.model
        assert updated.llm.timeout_seconds == settings.llm.timeout_seconds
        assert updated.generation == settings.generation
        assert settings.llm.temperature == pytest.approx(0.0)
        assert settings.llm.max_tokens == 1_000
        assert settings.llm.context_window_tokens is None
        assert settings.llm.structured_output_mode is StructuredOutputMode.JSON_SCHEMA

    @staticmethod
    def test_accepts_temperature_zero_and_enum_override() -> None:
        settings: AppSettings = with_llm_updates(make_settings(), temperature=0.7)

        updated: AppSettings = with_llm_updates(
            settings,
            temperature=0.0,
            structured_output_mode=StructuredOutputMode.JSON_OBJECT,
        )

        assert updated.llm.temperature == pytest.approx(0.0)
        assert updated.llm.structured_output_mode is StructuredOutputMode.JSON_OBJECT
        assert settings.llm.temperature == pytest.approx(0.7)

    @pytest.mark.parametrize(
        "updates",
        [
            {"temperature": 10.0},
            {"max_tokens": 0},
            {"max_tokens": -1},
            {"unknown_parameter": True},
            {"structured_output_mode": "not_a_mode"},
        ],
    )
    @staticmethod
    def test_invalid_overrides_raise_validation_error(
        updates: dict[str, object]
    ) -> None:
        settings: AppSettings = make_settings()

        with pytest.raises(ValidationError):
            with_llm_updates(settings, **updates)

        assert settings.llm.temperature == pytest.approx(0.0)
        assert settings.llm.max_tokens == 1_000
