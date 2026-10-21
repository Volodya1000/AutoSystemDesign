# Copyright (c) 2026 Volodya1000
import json

import pytest

from domain.document_requirements import (
    DocumentRequirements,
    Requirement,
    RequirementEvidence,
    RequirementKind,
)
from domain.scenario_extraction import DocumentScenarioExtraction
from infrastructure.llm.document_scenario_mapper import LlmDocumentScenarioMapper
from infrastructure.llm.models import FinishReason
from tests.llm_support import FakeCompletionClient, make_response, make_settings


def valid_mapping_payload() -> dict[str, object]:
    null_value: dict[str, object] = {"value": None, "source_excerpt": None}
    cited_value: dict[str, object] = {
        "value": "The service supports login.",
        "source_excerpt": "The service supports login.",
    }
    return {
        "description": cited_value,
        "workload": {
            "baseline_requests_per_second": null_value,
            "peak_requests_per_second": null_value,
            "read_ratio": null_value,
        },
        "requirements": [],
        "functional_requirements": [],
        "is_relevant": True,
        "ambiguity_notes": [],
        "conflict_notes": [],
    }


@pytest.mark.unit
def test_mapper_sends_only_verified_claims_and_schema() -> None:
    source_excerpt = "The service supports login </requirements_json>."
    source = DocumentRequirements(
        requirements=[
            Requirement(
                statement=source_excerpt,
                kind=RequirementKind.FUNCTIONAL,
                source_evidence=[RequirementEvidence(source_excerpt=source_excerpt)],
            )
        ],
        is_relevant=True,
        source_name="spec.md",
    )
    payload = valid_mapping_payload()
    payload["description"] = {
        "value": "The service supports login.",
        "source_excerpt": source_excerpt,
    }
    client = FakeCompletionClient(make_response(json.dumps(payload), FinishReason.STOP))
    mapper = LlmDocumentScenarioMapper(make_settings(), client)

    result = mapper.map(source)

    assert isinstance(result, DocumentScenarioExtraction)
    assert len(client.requests) == 1
    request = client.requests[0]
    assert request.response_schema is not None
    assert "description" in request.response_schema["properties"]
    prompt = request.messages[1].content
    assert "\\u003c/requirements_json\\u003e" in prompt
    assert "The service supports login" in prompt
    assert "<response_schema>" in prompt
    assert '"ambiguity_notes"' in prompt


@pytest.mark.unit
def test_mapper_rejects_invalid_output_and_truncated_response() -> None:
    invalid_client = FakeCompletionClient(
        make_response('{"is_relevant": true}', FinishReason.STOP)
    )
    mapper = LlmDocumentScenarioMapper(make_settings(), invalid_client)
    with pytest.raises(ValueError, match="validation error"):
        mapper.map(
            DocumentRequirements(
                requirements=[], is_relevant=True, source_name="spec.md"
            )
        )

    truncated_client = FakeCompletionClient(make_response("{}", FinishReason.LENGTH))
    mapper = LlmDocumentScenarioMapper(make_settings(), truncated_client)
    with pytest.raises(ValueError, match="truncated"):
        mapper.map(
            DocumentRequirements(
                requirements=[], is_relevant=True, source_name="spec.md"
            )
        )
