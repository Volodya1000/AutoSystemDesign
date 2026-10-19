from pathlib import Path

import pytest

from application.requirements_extraction import DocumentRequirementsService
from domain.document_requirements import (
    Requirement,
    RequirementEvidence,
    RequirementIssueKind,
    RequirementKind,
)
from domain.extraction_chunk import ExtractionChunk
from infrastructure.document_readers.markdown_reader import MarkdownReader


class FakeExtractor:
    def __init__(self) -> None:
        self.inputs: list[str] = []

    def extract(self, text: str, source_name: str) -> ExtractionChunk:
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
        def extract(self, text: str, source_name: str) -> ExtractionChunk:
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
    assert any(
        issue.kind is RequirementIssueKind.UNSUPPORTED_EVIDENCE
        for issue in result.issues
    )
    assert result.is_relevant
