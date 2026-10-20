"""Tests for pure document-to-scenario transformation functions."""

import pytest

from application.document_scenario_functions import build_workload, resolve_candidate
from application.document_scenario_functions.evidence import CandidateValidationOptions
from domain.scenario_extraction import EvidenceValue, ExtractedWorkload


@pytest.mark.unit
def test_resolve_candidate_returns_evidence_without_mutating_inputs() -> None:
    excerpt = "A customer can update a shopping cart."
    verified_excerpts = [excerpt]
    candidate = EvidenceValue[str](value=excerpt, source_excerpt=excerpt)

    result = resolve_candidate(
        candidate,
        "description",
        verified_excerpts,
        options=CandidateValidationOptions(required=True, verbatim_text=True),
    )

    assert result.value == excerpt
    assert result.field_evidence == (("description", excerpt),)
    assert not result.issues
    assert verified_excerpts == [excerpt]


@pytest.mark.unit
def test_build_workload_does_not_mutate_candidates_or_verified_excerpts() -> None:
    baseline = "The system supports 120 requests per second."
    peak = "Traffic can reach 400 requests per second."
    ratio = "Read requests account for 0.7 of total traffic."
    verified_excerpts = [baseline, peak, ratio]
    extracted = ExtractedWorkload(
        baseline_requests_per_second=EvidenceValue[float](
            value=120.0,
            source_excerpt=baseline,
        ),
        peak_requests_per_second=EvidenceValue[float](
            value=400.0,
            source_excerpt=peak,
        ),
        read_ratio=EvidenceValue[float](
            value=0.7,
            source_excerpt=ratio,
        ),
    )
    original_payload = extracted.model_dump()

    result = build_workload(extracted, verified_excerpts)

    assert result.value is not None
    assert result.value.baseline_requests_per_second == EXPECTED_ASSERT_RESULT_VALUE_BASELINE_REQUESTS_PE
    assert result.value.peak_requests_per_second == EXPECTED_ASSERT_RESULT_VALUE_PEAK_REQUESTS_PER_SE
    assert result.value.read_ratio == EXPECTED_ASSERT_RESULT_VALUE_READ_RATIO
    assert result.field_evidence == (
        ("workload.baseline_requests_per_second", baseline),
        ("workload.peak_requests_per_second", peak),
        ("workload.read_ratio", ratio),
    )
    assert extracted.model_dump() == original_payload
    assert verified_excerpts == [baseline, peak, ratio]

EXPECTED_ASSERT_RESULT_VALUE_READ_RATIO = 0.7
EXPECTED_ASSERT_RESULT_VALUE_PEAK_REQUESTS_PER_SE = 400.0
EXPECTED_ASSERT_RESULT_VALUE_BASELINE_REQUESTS_PE = 120.0
