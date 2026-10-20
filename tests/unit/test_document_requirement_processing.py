import pytest

from application.document_processing import (
    deduplicate_issues,
    deduplicate_requirements,
    is_evidence_supported,
    matches_verified_excerpt,
    split_document_text,
)
from domain.document_requirements import (
    Requirement,
    RequirementEvidence,
    RequirementIssue,
    RequirementIssueKind,
    RequirementKind,
)


@pytest.mark.unit
def test_split_document_text_keeps_chunks_within_limit() -> None:
    text = "\n\n".join(f"Requirement paragraph {index}." for index in range(20))

    chunks = split_document_text(text, max_chars=50, overlap_chars=8)

    assert len(chunks) > 1
    assert all(0 < len(chunk) <= 50 for chunk in chunks)
    assert all(chunk in text for chunk in chunks)


@pytest.mark.unit
def test_split_document_text_rejects_invalid_overlap() -> None:
    with pytest.raises(ValueError, match="overlap_chars"):
        split_document_text("text", max_chars=10, overlap_chars=10)


@pytest.mark.unit
def test_split_document_text_returns_empty_list_for_empty_text() -> None:
    assert not split_document_text("", max_chars=10, overlap_chars=0)


@pytest.mark.unit
def test_deduplicate_requirements_preserves_distinct_source_evidence() -> None:
    first = Requirement(
        statement="The service MUST support login.",
        kind=RequirementKind.FUNCTIONAL,
        source_evidence=[
            RequirementEvidence(source_excerpt="The service MUST support login.")
        ],
    )
    duplicate = Requirement(
        statement="the service must support login.",
        kind=RequirementKind.FUNCTIONAL,
        source_evidence=[
            RequirementEvidence(source_excerpt="Customers can log in to the service.")
        ],
    )
    different_kind = Requirement(
        statement="the service must support login.",
        kind=RequirementKind.NON_FUNCTIONAL,
        source_evidence=[
            RequirementEvidence(source_excerpt="Customers can log in to the service.")
        ],
    )

    result = deduplicate_requirements([first, duplicate, different_kind])

    assert len(result) == 2
    assert result[0].source_evidence == [
        RequirementEvidence(source_excerpt="The service MUST support login."),
        RequirementEvidence(source_excerpt="Customers can log in to the service."),
    ]
    assert result[1].kind is RequirementKind.NON_FUNCTIONAL


@pytest.mark.unit
def test_evidence_validation_ignores_whitespace_but_not_changed_words() -> None:
    evidence = RequirementEvidence(source_excerpt="The service\n supports login.")

    assert is_evidence_supported(evidence, "The service supports\n\nlogin.")
    assert not is_evidence_supported(evidence, "The service might support login.")


@pytest.mark.unit
def test_deduplicate_issues_preserves_all_distinct_evidence() -> None:
    first = RequirementIssue(
        kind=RequirementIssueKind.AMBIGUOUS,
        description="The statement is unclear.",
        evidence=["Source excerpt A."],
    )
    duplicate = RequirementIssue(
        kind=RequirementIssueKind.AMBIGUOUS,
        description="  The statement is unclear. ",
        evidence=["Source excerpt B."],
    )

    result = deduplicate_issues([first, duplicate])

    assert len(result) == 1
    assert result[0].evidence == ["Source excerpt A.", "Source excerpt B."]


@pytest.mark.unit
def test_scenario_citation_must_match_a_complete_verified_excerpt() -> None:
    assert matches_verified_excerpt(
        "The service   supports login.", ["The service\nsupports login."]
    )
    assert not matches_verified_excerpt(
        "supports login.", ["The service supports login."]
    )
