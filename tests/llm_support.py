# Copyright (c) 2026 Volodya1000
"""Shared fake client and settings for structured-output adapter tests."""

from pydantic import SecretStr

from application.usage import TokenUsage
from config.llm import LlmSettings, StructuredOutputMode
from config.root import AppSettings
from infrastructure.llm.models import CompletionRequest, CompletionResult, FinishReason


class FakeCompletionClient:
    """Capture completion requests and return a deterministic configured response."""

    def __init__(self, response: CompletionResult) -> None:
        self.response = response
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> CompletionResult:
        """Store the request and return the configured result."""
        self.requests.append(request)
        return self.response


def make_settings() -> AppSettings:
    """Build settings that never require real credentials or an endpoint."""
    return AppSettings(
        base_url="http://localhost:1234/v1",
        api_key=SecretStr("unit-test-key"),
        llm=LlmSettings(
            model="openai/test-model",
            temperature=0.0,
            max_tokens=1_000,
            timeout_seconds=10.0,
            structured_output_mode=StructuredOutputMode.JSON_SCHEMA,
        ),
    )


def make_response(content: str, finish_reason: FinishReason) -> CompletionResult:
    """Build a typed completion result for unit tests."""
    return CompletionResult(
        model="test-model",
        content=content,
        finish_reason=finish_reason,
        usage=TokenUsage(),
    )
