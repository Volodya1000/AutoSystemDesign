"""LLM sampling settings owned by config.yaml.

Connection fields (base_url, api_key) are intentionally NOT here: they live
on AppSettings and are environment-only.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class StructuredOutputMode(StrEnum):
    """How structured output is requested from the provider."""

    PROMPT = "prompt"  # schema only in the prompt text (max compatibility)
    JSON_OBJECT = "json_object"
    JSON_SCHEMA = "json_schema"


class LlmSettings(BaseModel):
    """YAML-owned LLM settings; no defaults: values always come from config.yaml.

    The provider prefix in `model` ("lm_studio/..." or "openai/...") selects
    the litellm dialect; both work against an OpenAI-compatible base_url.
    """

    model_config = ConfigDict(extra="forbid")

    model: str
    temperature: float = Field(ge=0, le=2.0)
    max_tokens: int = Field(gt=0)
    context_window_tokens: int | None = Field(default=None, gt=0)
    timeout_seconds: float = Field(gt=0)
    structured_output_mode: StructuredOutputMode
