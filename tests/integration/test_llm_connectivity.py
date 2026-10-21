import logging

import httpx
import pytest

from config.root import AppSettings
from infrastructure.llm.client import LiteLlmClient
from infrastructure.llm.models import (
    CompletionRequest,
    FinishReason,
    Message,
    MessageRole,
)

pytestmark = pytest.mark.integration

_logger: logging.Logger = logging.getLogger(__name__)

_KNOWN_PROVIDER_PREFIXES: tuple[str, ...] = ("lm_studio/", "openai/")


def _strip_provider_prefix(model: str) -> str:
    for prefix in _KNOWN_PROVIDER_PREFIXES:
        if model.startswith(prefix):
            return model[len(prefix) :]
    return model


@pytest.mark.usefixtures("require_lm_studio")
def test_model_is_listed(gate_settings: AppSettings) -> None:
    response: httpx.Response = httpx.get(
        f"{gate_settings.base_url}/models", timeout=5.0
    )
    available_ids: list[str] = [entry["id"] for entry in response.json()["data"]]
    expected_id: str = _strip_provider_prefix(gate_settings.llm.model)
    if expected_id not in available_ids:
        pytest.fail(
            f"Model '{expected_id}' (from config '{gate_settings.llm.model}') is not "
            f"loaded in LM Studio. Available models: {available_ids}"
        )
    _logger.info("Model '%s' is served by LM Studio", expected_id)


@pytest.mark.usefixtures("require_lm_studio")
def test_completion_returns_content_and_usage(
    gate_settings: AppSettings,
) -> None:
    client: LiteLlmClient = LiteLlmClient(settings=gate_settings)
    result = client.complete(
        CompletionRequest(
            messages=[
                Message(
                    role=MessageRole.USER, content="Reply with the single word: ready"
                )
            ],
            max_tokens=16,
        )
    )
    assert result.content.strip()
    assert result.usage.total_tokens > 0
    assert result.latency_seconds > 0.0
    assert result.finish_reason in {
        FinishReason.STOP,
        FinishReason.LENGTH,
        FinishReason.OTHER,
    }
