"""Diagnostics for provider-side context-window overflow errors."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from infrastructure.llm.models import CompletionRequest


_CONTEXT_OVERFLOW_MARKERS: tuple[str, ...] = (
    "context size has been exceeded",
    "maximum context length",
    "context_length_exceeded",
    "context window exceeded",
)


def context_overflow_diagnostic(
    error: Exception,
    request: CompletionRequest,
    *,
    model: str,
    context_window_tokens: int | None,
) -> str | None:
    """Explain estimated token demand when the provider rejects an oversized prompt.

    Token counts are estimates because local OpenAI-compatible servers often
    reject requests before returning usage information.
    """
    message = str(error)
    normalized_message = message.casefold()
    if not any(marker in normalized_message for marker in _CONTEXT_OVERFLOW_MARKERS):
        return None

    try:
        import litellm

        prompt_tokens = int(
            litellm.token_counter(
                model=model,
                messages=[item.model_dump() for item in request.messages],
            )
        )
    except (ValueError, TypeError, KeyError, AttributeError):  # token counter is best-effort
        prompt_tokens = None

    details = ["LLM context window exceeded."]
    if prompt_tokens is None:
        details.append("Estimated prompt tokens: unavailable.")
    else:
        required_tokens = prompt_tokens + request.max_tokens
        details.append(
            f"Estimated prompt tokens: {prompt_tokens}; "
            f"reserved completion tokens: {request.max_tokens}; "
            f"estimated required context: about {required_tokens} tokens."
        )

    if context_window_tokens is None:
        details.append(
            "Context limit: unknown (the endpoint did not report it); "
            "set llm.context_window_tokens to compare against the model's "
            "configured limit."
        )
    else:
        details.append(f"Configured context limit: {context_window_tokens} tokens.")
        if prompt_tokens is not None:
            required_tokens = prompt_tokens + request.max_tokens
            excess = max(0, required_tokens - context_window_tokens)
            if excess:
                details.append(f"Estimated excess over limit: about {excess} tokens.")
            else:
                details.append(
                    "Estimated prompt plus reserved completion fits the configured "
                    "limit; actual tokenization or server-side overhead may differ."
                )

    return " ".join(details)
