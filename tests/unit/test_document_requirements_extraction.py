from pathlib import Path

import pytest

from application.requirements_extraction import (
    DocumentRequirementsService,
    ExtractionChunk,
)
from domain.document_requirements import Requirement, RequirementKind
from infrastructure.document_readers.markdown_reader import MarkdownReader


class FakeExtractor:
    def __init__(self) -> None:
        self.inputs: list[str] = []

    def extract(self, text: str, source_name: str) -> ExtractionChunk:
        self.inputs.append(text)
        requirement = Requirement(
            statement="The service must support login.",
            kind=RequirementKind.FUNCTIONAL,
            source_excerpt="The service must support login.",
        )
        return ExtractionChunk(requirements=[requirement], is_relevant=True)


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


@pytest.mark.unit
def test_reports_missing_required_fields(tmp_path: Path) -> None:
    path = tmp_path / "spec.md"
    path.write_text("The service must support login.", encoding="utf-8")

    class EmptyExtractor:
        def extract(self, text: str, source_name: str) -> ExtractionChunk:
            return ExtractionChunk(is_relevant=False)

    result = DocumentRequirementsService(
        MarkdownReader(), EmptyExtractor(), required_fields=("load_profile",)
    ).extract_file(path)

    assert any(issue.field == "load_profile" for issue in result.issues)
    assert not result.is_relevant
