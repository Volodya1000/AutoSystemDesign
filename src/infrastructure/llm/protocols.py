"""Protocols for infrastructure-level LLM transport adapters."""

from typing import Protocol

from infrastructure.llm.models import CompletionRequest, CompletionResult


class CompletionClient(Protocol):
    """Structural contract shared by the production client and test doubles."""

    def complete(self, request: CompletionRequest) -> CompletionResult:
        """Send a typed request and return a normalized completion result."""
