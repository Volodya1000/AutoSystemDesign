# pylint: disable=wrong-import-position
"""Thin synchronous adapter over litellm.completion for local endpoints."""

import logging
import os
import time
from typing import Any, Final

os.environ.setdefault("LITELLM_LOG", "ERROR")  # must run before importing litellm

import litellm

from application.usage import TokenUsage
from config.root import AppSettings
from domain.models.topology import ArchitectureGraph
from infrastructure.exceptions.llm_exceptions import LlmConnectionError
from infrastructure.llm.models import (
    CompletionRequest,
    CompletionResult,
    FinishReason,
)

litellm.suppress_debug_info = True

_ARCHITECTURE_GRAPH_SCHEMA_NAME: Final[str] = "architecture_graph"


class LiteLlmClient:
    """Typed transport adapter over litellm.completion.

    Knows litellm only: converts transport failures into LlmConnectionError,
    takes usage from the endpoint (falling back to litellm.token_counter),
    and measures latency. Knows nothing about graphs or prompts.
    """

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self.logger: logging.Logger = logging.getLogger(self.__class__.__name__)

    def complete(self, request: CompletionRequest) -> CompletionResult:
        call_kwargs: dict[str, Any] = {
            "model": self._settings.llm.model,
            "api_base": self._settings.base_url,
            "api_key": self._settings.api_key.get_secret_value(),
            "messages": [message.model_dump() for message in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "timeout": request.timeout_seconds,
            "drop_params": True,
            "num_retries": 0,
        }
        response_format: dict[str, Any] | None = self._build_response_format()
        if response_format is not None:
            call_kwargs["response_format"] = response_format

        start_time: float = time.perf_counter()
        try:
            response: Any = litellm.completion(**call_kwargs)
        except Exception as error:
            self.logger.error(
                "LLM call to %s failed: %s", self._settings.base_url, error
            )
            raise LlmConnectionError(
                base_url=self._settings.base_url,
                model=self._settings.llm.model,
                original_message=str(error),
            ) from error
        latency_seconds: float = time.perf_counter() - start_time

        result: CompletionResult = self._to_completion_result(
            response, request, latency_seconds
        )
        self.logger.info(
            "LLM completion: model=%s latency=%.1fs tokens=%d finish_reason=%s",
            result.model,
            latency_seconds,
            result.usage.total_tokens,
            result.finish_reason.value,
        )
        return result

    def _build_response_format(self) -> dict[str, Any] | None:
        mode = self._settings.llm.structured_output_mode
        if mode.value == "prompt":
            return None
        if mode.value == "json_object":
            return {"type": mode.value}
        return {
            "type": mode.value,
            "json_schema": {
                "name": _ARCHITECTURE_GRAPH_SCHEMA_NAME,
                "schema": ArchitectureGraph.model_json_schema(),
                "strict": True,
            },
        }

    def _to_completion_result(
        self, response: Any, request: CompletionRequest, latency_seconds: float
    ) -> CompletionResult:
        choices: list[Any] = getattr(response, "choices", None) or []
        content: str = ""
        raw_finish_reason: str | None = None
        if choices:
            first_choice: Any = choices[0]
            message: Any = getattr(first_choice, "message", None)
            content = getattr(message, "content", None) or ""  # reasoning models
            raw_finish_reason = getattr(first_choice, "finish_reason", None)
        model_name: str = getattr(response, "model", None) or self._settings.llm.model
        return CompletionResult(
            model=model_name,
            content=content,
            finish_reason=FinishReason.from_raw(raw_finish_reason),
            usage=self._extract_usage(response, request, content),
            latency_seconds=latency_seconds,
        )

    def _extract_usage(
        self, response: Any, request: CompletionRequest, content: str
    ) -> TokenUsage:
        raw_usage: Any = getattr(response, "usage", None)
        prompt_tokens: int = int(getattr(raw_usage, "prompt_tokens", 0) or 0)
        completion_tokens: int = int(getattr(raw_usage, "completion_tokens", 0) or 0)
        if prompt_tokens > 0 or completion_tokens > 0:
            return TokenUsage(
                prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
            )
        return self._estimate_usage(request, content)

    def _estimate_usage(self, request: CompletionRequest, content: str) -> TokenUsage:
        """Fallback counting when the endpoint does not report usage."""
        try:
            prompt_tokens: int = int(
                litellm.token_counter(
                    model=self._settings.llm.model,
                    messages=[message.model_dump() for message in request.messages],
                )
            )
            completion_tokens: int = (
                int(litellm.token_counter(model=self._settings.llm.model, text=content))
                if content
                else 0
            )
        except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            # token_counter may fail for many provider/dependency reasons;
            # the usage fallback must never break the actual completion.
            return TokenUsage(prompt_tokens=0, completion_tokens=0, estimated=True)
        return TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            estimated=True,
        )
