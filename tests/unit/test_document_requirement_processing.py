import pytest

from application.document_processing import (
    deduplicate_requirements,
    split_document_text,
)
from domain.document_requirements import Requirement, RequirementKind


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
    assert split_document_text("", max_chars=10, overlap_chars=0) == []


@pytest.mark.unit
def test_deduplicate_requirements_uses_kind_and_normalized_statement() -> None:
    first = Requirement(
        statement="  The service MUST support login. ",
        kind=RequirementKind.FUNCTIONAL,
        source_excerpt="The service MUST support login.",
    )
    duplicate = Requirement(
        statement="the service must support login.",
        kind=RequirementKind.FUNCTIONAL,
        source_excerpt="Login must be supported.",
    )
    different_kind = Requirement(
        statement="the service must support login.",
        kind=RequirementKind.NON_FUNCTIONAL,
        source_excerpt="Login must be supported.",
    )

    result = deduplicate_requirements([first, duplicate, different_kind])

    assert result == [first, different_kind]
