from pathlib import Path

import pytest

from application.requirements_extraction import DocumentRequirementsService
from domain.document_requirements import (
    Requirement,
    RequirementEvidence,
    RequirementIssueKind,
    RequirementKind,
    SourceBackedNote,
)
from domain.extraction_chunk import ExtractionChunk
from infrastructure.document_readers.markdown_reader import MarkdownReader
from tests.test_support import has_issue


class FakeExtractor:
    def __init__(self) -> None:
        self.inputs: list[str] = []

    def extract(self, text: str, _source_name: str) -> ExtractionChunk:
        self.inputs.append(text)
        requirement = Requirement(
            statement="A requirement paragraph.",
            kind=RequirementKind.FUNCTIONAL,
            source_evidence=[
                RequirementEvidence(source_excerpt="A requirement paragraph.")
            ],
        )
        return ExtractionChunk(
            requirements=[requirement],
            is_relevant=True,
            ambiguity_notes=[],
            conflict_notes=[],
        )


@pytest.mark.unit
def test_splits_large_documents_and_deduplicates_results(tmp_path: Path) -> None:
    path = tmp_path / "spec.md"
    path.write_text("\n\n".join(["A requirement paragraph."] * 8), encoding="utf-8")
    extractor = FakeExtractor()
    service = DocumentRequirementsService(
        MarkdownReader(), extractor, max_chars=40, overlap_chars=5
    )

    result = service.extract_file(path)

    assert len(extractor.inputs) > 1
    assert all(len(chunk) <= 40 for chunk in extractor.inputs)
    assert len(result.requirements) == 1
    assert result.is_relevant
    assert result.requirements[0].source_evidence == [
        RequirementEvidence(source_excerpt="A requirement paragraph.")
    ]


@pytest.mark.unit
def test_discards_requirement_without_source_grounded_evidence(tmp_path: Path) -> None:
    path = tmp_path / "spec.md"
    path.write_text("The system can process orders.", encoding="utf-8")

    class HallucinatingExtractor:
        def extract(self, _text: str, _source_name: str) -> ExtractionChunk:
            requirement = Requirement(
                statement="The system supports biometric login.",
                kind=RequirementKind.FUNCTIONAL,
                source_evidence=[
                    RequirementEvidence(
                        source_excerpt="The system supports biometric login."
                    )
                ],
            )
            return ExtractionChunk(
                requirements=[requirement],
                is_relevant=True,
                ambiguity_notes=[],
                conflict_notes=[],
            )

    result = DocumentRequirementsService(
        MarkdownReader(), HallucinatingExtractor()
    ).extract_file(path)

    assert not result.requirements
    assert has_issue(result.issues, RequirementIssueKind.UNSUPPORTED_EVIDENCE)
    assert result.is_relevant


@pytest.mark.unit
def test_rejects_paraphrased_claim_even_when_its_citation_exists(
    tmp_path: Path,
) -> None:
    source_excerpt = "The service may process orders."
    path = tmp_path / "spec.md"
    path.write_text(source_excerpt, encoding="utf-8")

    class ParaphrasingExtractor:
        def extract(self, _text: str, _source_name: str) -> ExtractionChunk:
            return ExtractionChunk(
                requirements=[
                    Requirement(
                        statement="The service guarantees exactly-once payments.",
                        kind=RequirementKind.FUNCTIONAL,
                        source_evidence=[
                            RequirementEvidence(source_excerpt=source_excerpt)
                        ],
                    )
                ],
                is_relevant=True,
                ambiguity_notes=[],
                conflict_notes=[],
            )

    result = DocumentRequirementsService(
        MarkdownReader(), ParaphrasingExtractor()
    ).extract_file(path)

    assert not result.requirements
    assert any(
        issue.kind is RequirementIssueKind.UNSUPPORTED_EVIDENCE
        and "does not exactly match" in issue.description
        for issue in result.issues
    )


@pytest.mark.unit
def test_rejects_ambiguity_note_with_fabricated_evidence(tmp_path: Path) -> None:
    source_excerpt = "The system can process orders."
    path = tmp_path / "spec.md"
    path.write_text(source_excerpt, encoding="utf-8")

    class HallucinatingNoteExtractor:
        def extract(self, _text: str, _source_name: str) -> ExtractionChunk:
            return ExtractionChunk(
                requirements=[
                    Requirement(
                        statement=source_excerpt,
                        kind=RequirementKind.FUNCTIONAL,
                        source_evidence=[
                            RequirementEvidence(source_excerpt=source_excerpt)
                        ],
                    )
                ],
                is_relevant=True,
                ambiguity_notes=[
                    SourceBackedNote(
                        description="The system is required to use biometric login.",
                        source_evidence=[
                            RequirementEvidence(source_excerpt=source_excerpt)
                        ],
                    )
                ],
                conflict_notes=[],
            )

    result = DocumentRequirementsService(
        MarkdownReader(), HallucinatingNoteExtractor()
    ).extract_file(path)

    assert any(
        issue.kind is RequirementIssueKind.UNSUPPORTED_EVIDENCE
        and "Discarded ambiguity note" in issue.description
        for issue in result.issues
    )
    assert not has_issue(
        result.issues,
        RequirementIssueKind.AMBIGUOUS,
        description_contains="biometric login",
    )
