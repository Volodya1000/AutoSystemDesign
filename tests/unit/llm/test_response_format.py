"""Unit tests of the LiteLlmClient response_format contract.

The behaviour under test is what the adapter sends to ``litellm.completion``
in each structured-output mode, so the tests patch ``litellm.completion``
and inspect the captured kwargs. This keeps the tests on the public
``complete()`` surface instead of reaching into ``_build_response_format``.
"""

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from config.llm import LlmSettings, StructuredOutputMode
from config.root import AppSettings
from infrastructure.llm.client import LiteLlmClient
from infrastructure.llm.models import CompletionRequest, Message, MessageRole

pytestmark = pytest.mark.unit

_COMPLETION_TARGET = "infrastructure.llm.client.litellm.completion"


def _client(mode: StructuredOutputMode) -> LiteLlmClient:
    settings = AppSettings(
        base_url="http://localhost:1234/v1",
        api_key=SecretStr("fake"),
        llm=LlmSettings(
            model="lm_studio/fake",
            temperature=0.0,
            max_tokens=64,
            timeout_seconds=5.0,
            structured_output_mode=mode,
        ),
    )
    return LiteLlmClient(settings=settings)


def _request(**kwargs: Any) -> CompletionRequest:
    return CompletionRequest(
        messages=[Message(role=MessageRole.USER, content="hi")],
        **kwargs,
    )


def _fake_response(content: str = "{}") -> SimpleNamespace:
    """Minimal object shaped like a litellm chat completion."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason="stop",
            )
        ],
        model="fake-model",
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
    )


def _captured_kwargs(mock_completion: Any) -> dict[str, Any]:
    """Returns the kwargs of the single call made to ``litellm.completion``."""
    assert mock_completion.call_count == 1
    kwargs: dict[str, Any] = dict(mock_completion.call_args.kwargs)
    return kwargs


def test_prompt_mode_sends_no_response_format() -> None:
    client = _client(StructuredOutputMode.PROMPT)
    with patch(_COMPLETION_TARGET, return_value=_fake_response()) as mocked:
        client.complete(_request())
    assert "response_format" not in _captured_kwargs(mocked)


def test_json_object_mode_does_not_need_a_schema() -> None:
    client = _client(StructuredOutputMode.JSON_OBJECT)
    with patch(_COMPLETION_TARGET, return_value=_fake_response()) as mocked:
        client.complete(_request())
    assert _captured_kwargs(mocked)["response_format"] == {"type": "json_object"}


def test_json_schema_mode_without_schema_raises_before_transport() -> None:
    client = _client(StructuredOutputMode.JSON_SCHEMA)
    with (
        patch(_COMPLETION_TARGET) as mocked,
        pytest.raises(ValueError, match="requires request.response_schema"),
    ):
        client.complete(_request())
    mocked.assert_not_called()


def test_json_schema_mode_passes_schema_through_unchanged() -> None:
    schema = {"type": "object", "properties": {"x": {"type": "string"}}}
    client = _client(StructuredOutputMode.JSON_SCHEMA)
    with patch(_COMPLETION_TARGET, return_value=_fake_response()) as mocked:
        client.complete(
            _request(response_schema=schema, response_schema_name="my_model")
        )
    assert _captured_kwargs(mocked)["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "my_model",
            "schema": schema,
            "strict": True,
        },
    }


def test_json_schema_mode_defaults_name_to_neutral_response() -> None:
    schema = {"type": "object"}
    client = _client(StructuredOutputMode.JSON_SCHEMA)
    with patch(_COMPLETION_TARGET, return_value=_fake_response()) as mocked:
        client.complete(_request(response_schema=schema))
    fmt = _captured_kwargs(mocked)["response_format"]
    assert fmt["json_schema"]["name"] == "response"
