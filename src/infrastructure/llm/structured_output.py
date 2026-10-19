"""Shared request handling for schema-constrained LLM completions."""

from typing import Any

from config.root import AppSettings
from infrastructure.llm.models import CompletionRequest, FinishReason, Message
from infrastructure.llm.protocols import CompletionClient


def complete_structured_response(
    settings: AppSettings,
    client: CompletionClient,
    messages: list[Message],
    response_schema: dict[str, Any],
    response_schema_name: str,
    operation: str,
) -> str:
    """Call the shared LLM client and validate the completion envelope."""
    request = CompletionRequest(
        messages=messages,
        temperature=0.0,
        max_tokens=min(settings.llm.max_tokens, 8_000),
        timeout_seconds=settings.llm.timeout_seconds,
        response_schema=response_schema,
        response_schema_name=response_schema_name,
    )
    response = client.complete(request)
    if response.finish_reason is FinishReason.LENGTH:
        raise ValueError(
            f"LLM {operation} response was truncated; reduce input size "
            "or increase the configured token limit."
        )
    if response.finish_reason is FinishReason.CONTENT_FILTER:
        raise ValueError(
            f"LLM {operation} was blocked by the provider's content filter."
        )
    if not response.content.strip():
        raise ValueError(f"LLM returned an empty {operation} response")
    return response.content
