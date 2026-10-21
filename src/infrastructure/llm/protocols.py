"""Protocol for the LLM completion transport consumed by agent adapters."""

from typing import Protocol

from infrastructure.llm.models import CompletionRequest, CompletionResult


class CompletionClientProtocol(Protocol):
    """Port exposing a single structured or unstructured completion call."""

    def complete(self, request: CompletionRequest) -> CompletionResult: ...
