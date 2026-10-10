"""Root application settings aggregating all groups.

Environment-only fields: `base_url` (ASD_BASE_URL) and `api_key`
(ASD_API_KEY, SecretStr). They cannot be set from the yaml config: the
loader explicitly refuses them at the top level, and the `llm` section has
no such fields (extra="forbid" on LlmSettings).

Sources, highest priority first: init kwargs, real environment variables,
.env file, yaml config file, field defaults. The .env file is a local
convenience for secrets; real environment variables always win over it.

The yaml config path defaults to config.yaml and can be redirected with the
APP_CONFIG_FILE environment variable (integration tests point it at
config.test.yaml).
"""

import os
from pathlib import Path
from typing import Any, Final

import yaml
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import (
    InitSettingsSource,
    PydanticBaseSettingsSource,
)

from config.generation import GenerationSettings
from config.llm import LlmSettings
from config.testing import IntegrationSettings

CONFIG_FILE_ENV_VAR: Final[str] = "APP_CONFIG_FILE"
_DEFAULT_CONFIG_FILE: Final[Path] = Path("config.yaml")
_ENV_OWNED_FIELDS: Final[frozenset[str]] = frozenset({"base_url", "api_key"})


def _load_yaml_config(config_file: Path) -> dict[str, Any]:
    """Parses the yaml config and refuses env-owned top-level fields.

    base_url and api_key must come from the environment (or .env) only;
    putting them into the config file is rejected loudly.
    """
    with config_file.open("r", encoding="utf-8") as stream:
        data: Any = yaml.safe_load(stream) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file {config_file} must contain a yaml mapping")
    misplaced: frozenset[str] = _ENV_OWNED_FIELDS & frozenset(data)
    if misplaced:
        raise ValueError(
            f"Config file {config_file} must not contain {sorted(misplaced)}: "
            "these fields are environment-only (ASD_BASE_URL / ASD_API_KEY)"
        )
    return data


class AppSettings(BaseSettings):
    """Single root settings object for the whole application."""

    model_config = SettingsConfigDict(
        env_prefix="ASD_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    base_url: str  # env only: ASD_BASE_URL
    api_key: SecretStr  # env only: ASD_API_KEY
    llm: LlmSettings
    generation: GenerationSettings = Field(default_factory=GenerationSettings)
    testing: IntegrationSettings = Field(default_factory=IntegrationSettings)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        config_file: Path = Path(
            os.environ.get(CONFIG_FILE_ENV_VAR, str(_DEFAULT_CONFIG_FILE))
        )
        sources: list[PydanticBaseSettingsSource] = [
            init_settings,
            env_settings,
            dotenv_settings,
        ]
        if config_file.exists():
            # The yaml data is loaded and guarded by us and injected as a
            # plain init-style source; the tuple order defines the priority.
            sources.append(
                InitSettingsSource(settings_cls, _load_yaml_config(config_file))
            )
        sources.append(file_secret_settings)
        return tuple(sources)


def load_app_settings() -> AppSettings:
    """Entry point: env vars, .env and the yaml config file."""
    return AppSettings()  # type: ignore[call-arg]  # fields come from sources


def with_llm_updates(settings: AppSettings, **updates: Any) -> AppSettings:
    """Returns a copy of the settings with LlmSettings fields overridden."""
    updated_llm: LlmSettings = settings.llm.model_copy(update=updates)
    return settings.model_copy(update={"llm": updated_llm})
