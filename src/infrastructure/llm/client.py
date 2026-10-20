"""litellm transport adapter: request assembly and response translation.

Request kwargs, response parsing, finish-reason mapping and logging stay
here because they describe the transport. Token accounting lives in
``usage_extractor`` and is delegated from ``_to_completion_result``.
"""

import logging
import time
from typing import Any, Final

import litellm

from config.root import AppSettings
from infrastructure.exceptions.llm_exceptions import LlmConnectionError
from infrastructure.llm.context_diagnostics import context_overflow_diagnostic
from infrastructure.llm.models import (
    CompletionRequest,
    CompletionResult,
    FinishReason,
)
from infrastructure.llm.usage_extractor import extract_usage

litellm.suppress_debug_info = True

_DEFAULT_SCHEMA_NAME: Final[str] = "response"


class ResponseSchemaRequiredError(ValueError):
    """JSON Schema mode was requested without a schema."""

    def __init__(self) -> None:
        super().__init__(
            "structured_output_mode='json_schema' requires request.response_schema; "
            "pass the target model's JSON Schema at the call site."
        )


class LiteLlmClient:
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
        response_format: dict[str, Any] | None = self._build_response_format(request)
        if response_format is not None:
            call_kwargs["response_format"] = response_format

        start_time: float = time.perf_counter()
        try:
            response: Any = litellm.completion(**call_kwargs)
        except Exception as error:
            diagnostic = context_overflow_diagnostic(
                error,
                request,
                model=self._settings.llm.model,
                context_window_tokens=self._settings.llm.context_window_tokens,
            )
            original_message = (
                f"{diagnostic} Provider error: {error}" if diagnostic else str(error)
            )
            self.logger.exception(
                "LLM call to %s failed: %s", self._settings.base_url, original_message
            )
            raise LlmConnectionError(
                base_url=self._settings.base_url,
                model=self._settings.llm.model,
                original_message=original_message,
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

    def _build_response_format(
        self, request: CompletionRequest
    ) -> dict[str, Any] | None:
        mode = self._settings.llm.structured_output_mode
        if mode.value == "prompt":
            return None
        if mode.value == "json_object":
            return {"type": mode.value}

        if request.response_schema is None:
            raise ResponseSchemaRequiredError
        name = request.response_schema_name or _DEFAULT_SCHEMA_NAME
        return {
            "type": mode.value,
            "json_schema": {
                "name": name,
                "schema": request.response_schema,
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
            content = getattr(message, "content", None) or ""
            raw_finish_reason = getattr(first_choice, "finish_reason", None)
        model_name: str = getattr(response, "model", None) or self._settings.llm.model
        return CompletionResult(
            model=model_name,
            content=content,
            finish_reason=FinishReason.from_raw(raw_finish_reason),
            usage=extract_usage(
                getattr(response, "usage", None),
                request,
                content,
                model=self._settings.llm.model,
            ),
            latency_seconds=latency_seconds,
        )
