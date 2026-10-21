# Copyright (c) 2026 Volodya1000
"""Shared request handling for schema-constrained LLM adapters."""

import json
from typing import TypeVar

from pydantic import BaseModel

from config.root import AppSettings
from infrastructure.llm.client import LiteLlmClient
from infrastructure.llm.models import (
    CompletionRequest,
    FinishReason,
    Message,
    MessageRole,
)
from infrastructure.llm.protocols import CompletionClient

EXPECTED_IF_LINES_COUNT = 3


class StructuredOutputError(ValueError):
    """The LLM response cannot be used as structured output."""


ModelT = TypeVar("ModelT", bound=BaseModel)


def encode_prompt_data(value: object) -> str:
    """JSON-encode untrusted prompt data without exposing markup delimiters."""
    encoded = json.dumps(value, ensure_ascii=False)
    return encoded.replace("<", "\\u003c").replace(">", "\\u003e")


def strip_markdown_json_fence(content: str) -> str:
    """Remove one enclosing Markdown JSON code fence, if present."""
    stripped = content.strip()
    lines = stripped.splitlines()
    if len(lines) < EXPECTED_IF_LINES_COUNT or lines[-1].strip() != "```":
        return stripped
    if lines[0].strip().lower() not in {"```", "```json"}:
        return stripped
    return "\n".join(lines[1:-1]).strip()


class StructuredOutputAdapter:
    """Share dependency setup, prompt assembly, and response validation."""

    def __init__(
        self,
        settings: AppSettings,
        client: CompletionClient | None = None,
    ) -> None:
        self._settings = settings
        self._client: CompletionClient = client or LiteLlmClient(settings)

    def complete_response(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[ModelT],
        response_schema_name: str,
        operation: str,
    ) -> ModelT:
        """Call the shared client and validate the response as a typed model."""
        request = CompletionRequest(
            messages=[
                Message(role=MessageRole.SYSTEM, content=system_prompt),
                Message(role=MessageRole.USER, content=user_prompt),
            ],
            temperature=0.0,
            max_tokens=min(self._settings.llm.max_tokens, 8_000),
            timeout_seconds=self._settings.llm.timeout_seconds,
            response_schema=response_model.model_json_schema(),
            response_schema_name=response_schema_name,
        )
        response = self._client.complete(request)
        if response.finish_reason is FinishReason.LENGTH:
            raise StructuredOutputError(
                f"LLM {operation} response was truncated; reduce input size "
                "or increase the configured token limit."
            )
        if response.finish_reason is FinishReason.CONTENT_FILTER:
            raise ValueError(
                f"LLM {operation} was blocked by the provider's content filter."
            )
        if not response.content.strip():
            raise ValueError(f"LLM returned an empty {operation} response")
        content = strip_markdown_json_fence(response.content)
        return response_model.model_validate_json(content)
