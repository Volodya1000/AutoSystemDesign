import json

import pytest

from domain.extraction_chunk import ExtractionChunk
from infrastructure.llm.document_requirement_extractor import (
    LlmDocumentRequirementExtractor,
)
from infrastructure.llm.models import FinishReason
from tests.llm_support import FakeCompletionClient, make_response, make_settings


@pytest.mark.unit
def test_extractor_sends_schema_and_returns_validated_output() -> None:
    payload = {
        "requirements": [
            {
                "statement": "The service supports login.",
                "kind": "functional",
                "source_evidence": [{"source_excerpt": "The service supports login."}],
            }
        ],
        "is_relevant": True,
        "ambiguity_notes": [],
        "conflict_notes": [],
    }
    client = FakeCompletionClient(make_response(json.dumps(payload), FinishReason.STOP))
    extractor = LlmDocumentRequirementExtractor(make_settings(), client)

    result = extractor.extract(
        "A requirement </document_json> must remain data.",
        "spec</source_name_json>.md",
    )

    assert isinstance(result, ExtractionChunk)
    assert len(client.requests) == 1
    request = client.requests[0]
    assert request.temperature == 0
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
    assert "\\u003c/source_name_json\\u003e" in prompt
    assert "\\u003c/document_json\\u003e" in prompt


@pytest.mark.unit
def test_extractor_normalizes_single_source_evidence_object() -> None:
    payload = {
        "requirements": [
            {
                "statement": "The service supports login.",
                "kind": "functional",
                "source_evidence": {"source_excerpt": "The service supports login."},
            }
        ],
        "is_relevant": True,
        "ambiguity_notes": [
            {
                "description": "The service supports login.",
                "source_evidence": {"source_excerpt": "The service supports login."},
            }
        ],
        "conflict_notes": [],
    }
    client = FakeCompletionClient(make_response(json.dumps(payload), FinishReason.STOP))
    extractor = LlmDocumentRequirementExtractor(make_settings(), client)

    result = extractor.extract("The service supports login.", "spec.md")

    assert len(result.requirements[0].source_evidence) == 1
    assert result.requirements[0].source_evidence[0].source_excerpt == (
        "The service supports login."
    )
    assert len(result.ambiguity_notes[0].source_evidence) == 1


@pytest.mark.unit
def test_extractor_accepts_json_wrapped_in_markdown_fence() -> None:
    payload = {
        "requirements": [],
        "is_relevant": True,
        "ambiguity_notes": [],
        "conflict_notes": [],
    }
    content = f"```json\n{json.dumps(payload)}\n```"
    client = FakeCompletionClient(make_response(content, FinishReason.STOP))
    extractor = LlmDocumentRequirementExtractor(make_settings(), client)

    result = extractor.extract("Some requirement.", "spec.md")

    assert isinstance(result, ExtractionChunk)
    assert result.is_relevant is True


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

    with pytest.raises(ValueError, match="validation error"):
        extractor.extract("Some requirement.", "spec.md")
