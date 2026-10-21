# Copyright (c) 2026 Volodya1000
"""Infrastructure-level LLM exceptions."""


class LlmConnectionError(Exception):
    """Transport-level failure while talking to the LLM endpoint.

    Covers network errors, timeouts and provider API errors reported by
    litellm; the original message is preserved.
    """

    def __init__(self, base_url: str, model: str, original_message: str) -> None:
        message: str = (
            f"LLM request to endpoint '{base_url}' for model '{model}': "
            f"{original_message}"
        )
        super().__init__(message)
        self.base_url = base_url
        self.model = model
        self.original_message = original_message
