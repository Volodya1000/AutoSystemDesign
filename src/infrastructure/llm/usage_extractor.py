"""Token-usage extraction from a raw litellm response.

Extracted from ``LiteLlmClient`` so the provider-usage / token-counter
fallback logic can be exercised without a live transport. This module is
free of logging and settings: it takes the bare inputs it needs
(``raw_usage``, the original ``CompletionRequest``, the completion
content, and the configured model name for token counting).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import litellm

from application.usage import TokenUsage

if TYPE_CHECKING:
    from infrastructure.llm.models import CompletionRequest


def extract_usage(
    raw_usage: object,
    request: CompletionRequest,
    content: str,
    *,
    model: str,
) -> TokenUsage:
    """Returns provider-reported tokens, or a token-count estimate.

    Providers that omit usage (some self-hosted endpoints, streaming
    shims) fall through to a best-effort local token count; the returned
    ``TokenUsage`` is marked ``estimated=True`` in that case.
    """
    prompt_tokens: int = int(getattr(raw_usage, "prompt_tokens", 0) or 0)
    completion_tokens: int = int(getattr(raw_usage, "completion_tokens", 0) or 0)
    if prompt_tokens > 0 or completion_tokens > 0:
        return TokenUsage(
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
        )
    return _estimate_usage(request, content, model=model)


def _estimate_usage(
    request: CompletionRequest, content: str, *, model: str
) -> TokenUsage:
    try:
        prompt_tokens: int = int(
            litellm.token_counter(
                model=model,
                messages=[message.model_dump() for message in request.messages],
            )
        )
        completion_tokens: int = (
            int(litellm.token_counter(model=model, text=content)) if content else 0
        )
    except (ValueError, KeyError, TypeError):
        return TokenUsage(prompt_tokens=0, completion_tokens=0, estimated=True)
    return TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        estimated=True,
    )
