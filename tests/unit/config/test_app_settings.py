# Copyright (c) 2026 Volodya1000
"""Unit tests of AppSettings env / .env / yaml source resolution."""

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from config.generation import GenerationSettings
from config.llm import LlmSettings, StructuredOutputMode
from config.root import CONFIG_FILE_ENV_VAR, AppSettings
from config.testing import IntegrationSettings

pytestmark = pytest.mark.unit

_ENV_ONLY_VALUES: dict[str, str] = {
    "ASD_BASE_URL": "http://localhost:1234/v1",
    "ASD_API_KEY": "lm-studio",
}

_LLM_YAML: str = (
    "llm:\n"
    "  model: lm_studio/yaml-model\n"
    "  temperature: 0.4\n"
    "  max_tokens: 1024\n"
    "  timeout_seconds: 30.0\n"
    "  structured_output_mode: prompt\n"
)


def _write_config_file(tmp_path: Path, content: str) -> None:
    (tmp_path / "config.yaml").write_text(content, encoding="utf-8")


def _write_env_file(tmp_path: Path, content: str) -> None:
    (tmp_path / ".env").write_text(content, encoding="utf-8")


def _set_env_only(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in _ENV_ONLY_VALUES.items():
        monkeypatch.setenv(name, value)


class TestAppSettings:
    @staticmethod
    def test_environment_provides_connection_fields(
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_env_only(monkeypatch)
        monkeypatch.setenv("ASD_LLM__MODEL", "lm_studio/env-model")
        monkeypatch.setenv("ASD_LLM__TEMPERATURE", "0.4")
        monkeypatch.setenv("ASD_LLM__MAX_TOKENS", "1024")
        monkeypatch.setenv("ASD_LLM__TIMEOUT_SECONDS", "30.0")
        monkeypatch.setenv("ASD_LLM__STRUCTURED_OUTPUT_MODE", "json_schema")
        settings: AppSettings = AppSettings()  # type: ignore[call-arg]
        assert settings.base_url == "http://localhost:1234/v1"
        assert settings.api_key.get_secret_value() == "lm-studio"
        assert settings.llm.model == "lm_studio/env-model"
        assert settings.llm.temperature == 0.4
        assert settings.llm.structured_output_mode is StructuredOutputMode.JSON_SCHEMA

    @staticmethod
    def test_env_file_provides_connection_fields(tmp_path: Path) -> None:
        _write_env_file(
            tmp_path,
            "ASD_BASE_URL=http://localhost:9999/v1\nASD_API_KEY=envfile-key\n",
        )
        _write_config_file(tmp_path, _LLM_YAML)
        settings: AppSettings = AppSettings()  # type: ignore[call-arg]
        assert settings.base_url == "http://localhost:9999/v1"
        assert settings.api_key.get_secret_value() == "envfile-key"
        assert settings.llm.model == "lm_studio/yaml-model"

    @staticmethod
    def test_real_environment_overrides_env_file(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _write_env_file(
            tmp_path,
            "ASD_BASE_URL=http://localhost:9999/v1\nASD_API_KEY=envfile-key\n",
        )
        _write_config_file(tmp_path, _LLM_YAML)
        monkeypatch.setenv("ASD_BASE_URL", "http://localhost:1234/v1")
        settings: AppSettings = AppSettings()  # type: ignore[call-arg]
        assert settings.base_url == "http://localhost:1234/v1"
        assert settings.api_key.get_secret_value() == "envfile-key"

    @staticmethod
    def test_yaml_provides_llm_section(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _set_env_only(monkeypatch)
        _write_config_file(tmp_path, _LLM_YAML + "generation:\n  max_attempts: 7\n")
        settings: AppSettings = AppSettings()  # type: ignore[call-arg]
        assert settings.llm.model == "lm_studio/yaml-model"
        assert settings.llm.temperature == 0.4
        assert settings.generation.max_attempts == 7
        assert settings.testing.generation_runs == 3  # untouched default

    @staticmethod
    def test_environment_overrides_yaml(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _set_env_only(monkeypatch)
        _write_config_file(tmp_path, _LLM_YAML)
        monkeypatch.setenv("ASD_LLM__MODEL", "lm_studio/env-model")
        settings: AppSettings = AppSettings()  # type: ignore[call-arg]
        assert settings.llm.model == "lm_studio/env-model"
        assert settings.llm.temperature == 0.4

    @staticmethod
    def test_config_file_env_var_redirects_yaml(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _set_env_only(monkeypatch)
        (tmp_path / "custom.yaml").write_text(_LLM_YAML, encoding="utf-8")
        monkeypatch.setenv(CONFIG_FILE_ENV_VAR, "custom.yaml")
        settings: AppSettings = AppSettings()  # type: ignore[call-arg]
        assert settings.llm.model == "lm_studio/yaml-model"

    @staticmethod
    def test_base_url_in_yaml_is_rejected(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _set_env_only(monkeypatch)
        _write_config_file(tmp_path, "base_url: http://localhost:1234/v1\n" + _LLM_YAML)
        # The yaml loader refuses env-owned fields with a plain ValueError.
        with pytest.raises(ValueError, match="must not contain"):
            AppSettings()  # type: ignore[call-arg]

    @staticmethod
    def test_base_url_inside_llm_section_is_rejected(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _set_env_only(monkeypatch)
        _write_config_file(
            tmp_path,
            "llm:\n"
            "  base_url: http://localhost:1234/v1\n"
            "  model: lm_studio/yaml-model\n"
            "  temperature: 0.4\n"
            "  max_tokens: 1024\n"
            "  timeout_seconds: 30.0\n"
            "  structured_output_mode: prompt\n",
        )
        with pytest.raises(ValidationError):
            AppSettings()  # type: ignore[call-arg]

    @staticmethod
    def test_unknown_environment_variable_is_rejected(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _set_env_only(monkeypatch)
        _write_config_file(tmp_path, _LLM_YAML)
        monkeypatch.setenv("ASD_LLM__TIEMOUT", "60")  # typo
        with pytest.raises(ValidationError):
            AppSettings()  # type: ignore[call-arg]

    @staticmethod
    def test_unknown_yaml_key_is_rejected(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _set_env_only(monkeypatch)
        _write_config_file(tmp_path, _LLM_YAML + "  tiemout: 60\n")
        with pytest.raises(ValidationError):
            AppSettings()  # type: ignore[call-arg]

    @staticmethod
    def test_full_init_kwargs() -> None:
        settings: AppSettings = AppSettings(
            base_url="http://localhost:1234/v1",
            api_key=SecretStr("fake"),
            llm=LlmSettings(
                model="lm_studio/test",
                temperature=0.7,
                max_tokens=512,
                timeout_seconds=12.5,
                structured_output_mode=StructuredOutputMode.PROMPT,
            ),
        )
        assert settings.generation == GenerationSettings()
        assert settings.testing == IntegrationSettings()
