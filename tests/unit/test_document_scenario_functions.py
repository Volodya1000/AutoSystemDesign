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
    assert result.value.baseline_requests_per_second == 120.0
    assert result.value.peak_requests_per_second == 400.0
    assert result.value.read_ratio == 0.7
    assert result.field_evidence == (
        ("workload.baseline_requests_per_second", baseline),
        ("workload.peak_requests_per_second", peak),
        ("workload.read_ratio", ratio),
    )
    assert extracted.model_dump() == original_payload
    assert verified_excerpts == [baseline, peak, ratio]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("ratio", "literal", "expected"),
    [
        ("Reads account for 80% of traffic.", 80.0, 0.8),
        ("Reads account for 1% of traffic.", 1.0, 0.01),
        ("Reads account for 0,8% of traffic.", 0.8, 0.008),
        ("The read fraction is 0.8.", 0.8, 0.8),
        ("The read fraction is 80.", 80.0, None),
        ("Reads account for 110% of traffic.", 110.0, None),
        ("Reads account for 80% of traffic.", 0.8, None),
        ("Reads are 80 and errors are 5%.", 80.0, None),
    ],
)
def test_workload_normalizes_only_source_backed_percentages(
    ratio: str, literal: float, expected: float | None
) -> None:
    baseline = "Normal load is 120 RPS."
    peak = "Peak load is 400 RPS."
    extracted = ExtractedWorkload(
        baseline_requests_per_second=EvidenceValue[float](
            value=120, source_excerpt=baseline
        ),
        peak_requests_per_second=EvidenceValue[float](value=400, source_excerpt=peak),
        read_ratio=EvidenceValue[float](value=literal, source_excerpt=ratio),
    )
    result = build_workload(extracted, [baseline, peak, ratio])
    if expected is None:
        assert result.value is None
        assert result.issues
    else:
        assert result.value is not None
        assert result.value.read_ratio == expected
        assert ("workload.read_ratio", ratio) in result.field_evidence
        assert not result.issues
    assert extracted.read_ratio.value == literal
