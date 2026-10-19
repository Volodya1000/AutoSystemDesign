"""Unit tests for actionable context-window overflow diagnostics."""

import litellm
import pytest

from infrastructure.llm.context_diagnostics import context_overflow_diagnostic
from infrastructure.llm.models import CompletionRequest, Message


@pytest.fixture
def completion_request() -> CompletionRequest:
    return CompletionRequest(
        messages=[Message(role="user", content="Generate an architecture.")],
        max_tokens=16_000,
    )


@pytest.mark.unit
def test_reports_estimated_demand_limit_and_excess(
    monkeypatch: pytest.MonkeyPatch,
    completion_request: CompletionRequest,
) -> None:
    monkeypatch.setattr(litellm, "token_counter", lambda **kwargs: 20_000)

    diagnostic = context_overflow_diagnostic(
        Exception("Error code: 400 - Context size has been exceeded."),
        completion_request,
        model="openai/qwen2.5-coder-14b-instruct",
        context_window_tokens=32_768,
    )

    assert diagnostic is not None
    assert "Estimated prompt tokens: 20000" in diagnostic
    assert "reserved completion tokens: 16000" in diagnostic
    assert "estimated required context: about 36000 tokens" in diagnostic
    assert "Configured context limit: 32768 tokens" in diagnostic
    assert "Estimated excess over limit: about 3232 tokens" in diagnostic


@pytest.mark.unit
def test_explains_when_endpoint_context_limit_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
    request: CompletionRequest,
) -> None:
    monkeypatch.setattr(litellm, "token_counter", lambda **kwargs: 20_000)

    diagnostic = context_overflow_diagnostic(
        Exception("maximum context length exceeded"),
        request,
        model="openai/qwen2.5-coder-14b-instruct",
        context_window_tokens=None,
    )

    assert diagnostic is not None
    assert "estimated required context: about 36000 tokens" in diagnostic
    assert "Context limit: unknown" in diagnostic
    assert "llm.context_window_tokens" in diagnostic


@pytest.mark.unit
def test_does_not_add_context_diagnostic_for_other_errors(
    request: CompletionRequest,
) -> None:
    diagnostic = context_overflow_diagnostic(
        Exception("Connection refused"),
        request,
        model="openai/qwen2.5-coder-14b-instruct",
        context_window_tokens=32_768,
    )

    assert diagnostic is None
