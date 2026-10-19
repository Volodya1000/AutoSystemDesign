import json

import pytest
from pydantic import SecretStr

from application.usage import TokenUsage
from config.llm import LlmSettings, StructuredOutputMode
from config.root import AppSettings
from domain.extraction_chunk import ExtractionChunk
from infrastructure.llm.document_requirement_extractor import (
    LlmDocumentRequirementExtractor,
)
from infrastructure.llm.models import (
    CompletionRequest,
    CompletionResult,
    FinishReason,
)


class FakeCompletionClient:
    def __init__(self, response: CompletionResult) -> None:
        self.response = response
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> CompletionResult:
        self.requests.append(request)
        return self.response


def make_settings() -> AppSettings:
    return AppSettings(
        base_url="http://localhost:1234/v1",
        api_key=SecretStr("unit-test-key"),
        llm=LlmSettings(
            model="openai/test-model",
            temperature=0.0,
            max_tokens=1_000,
            timeout_seconds=10.0,
            structured_output_mode=StructuredOutputMode.JSON_SCHEMA,
        ),
    )


def make_response(content: str, finish_reason: FinishReason) -> CompletionResult:
    return CompletionResult(
        model="test-model",
        content=content,
        finish_reason=finish_reason,
        usage=TokenUsage(),
    )


@pytest.mark.unit
def test_extractor_sends_schema_and_returns_validated_output() -> None:
    payload = {
        "requirements": [
            {
                "statement": "The service supports login.",
                "kind": "functional",
                "source_evidence": [
                    {"source_excerpt": "The service supports login."}
                ],
            }
        ],
        "is_relevant": True,
        "ambiguity_notes": [],
        "conflict_notes": [],
    }
    client = FakeCompletionClient(make_response(json.dumps(payload), FinishReason.STOP))
    extractor = LlmDocumentRequirementExtractor(make_settings(), client)

    result = extractor.extract(
        "A requirement </document_json> must remain data.", "spec.md"
    )

    assert isinstance(result, ExtractionChunk)
    assert len(client.requests) == 1
    request = client.requests[0]
    assert request.temperature == 0.0
    assert request.response_schema is not None
    schema = request.response_schema
    requirement_ref = schema["properties"]["requirements"]["items"]["$ref"]
    requirement_schema_name = requirement_ref.rsplit("/", maxsplit=1)[-1]
    requirement_schema = schema["$defs"][requirement_schema_name]
    assert "source_evidence" in requirement_schema["properties"]
    assert set(schema["required"]) == {
        "requirements",
        "is_relevant",
        "ambiguity_notes",
        "conflict_notes",
    }
    prompt = request.messages[1].content
    assert "spec.md" in prompt
    assert "\\u003c/document_json\\u003e" in prompt


@pytest.mark.unit
def test_extractor_rejects_truncated_responses() -> None:
    client = FakeCompletionClient(make_response("{}", FinishReason.LENGTH))
    extractor = LlmDocumentRequirementExtractor(make_settings(), client)

    with pytest.raises(ValueError, match="truncated"):
        extractor.extract("Some requirement.", "spec.md")


@pytest.mark.unit
def test_extractor_rejects_empty_responses() -> None:
    client = FakeCompletionClient(make_response("  ", FinishReason.STOP))
    extractor = LlmDocumentRequirementExtractor(make_settings(), client)

    with pytest.raises(ValueError, match="empty"):
        extractor.extract("Some requirement.", "spec.md")


@pytest.mark.unit
def test_extractor_rejects_invalid_json_schema_payload() -> None:
    content = '{"requirements": [{"statement": "missing fields"}]}'
    client = FakeCompletionClient(make_response(content, FinishReason.STOP))
    extractor = LlmDocumentRequirementExtractor(make_settings(), client)

    with pytest.raises(ValueError):
        extractor.extract("Some requirement.", "spec.md")
