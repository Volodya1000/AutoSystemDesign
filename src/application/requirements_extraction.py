"""Application service coordinating document reading and requirement extraction."""

from pathlib import Path
from typing import Protocol

from application.document_processing import (
    deduplicate_issues,
    deduplicate_requirements,
    split_document_text,
)
from application.document_reader import DocumentReader
from domain.document_requirements import (
    DocumentRequirements,
    RequirementIssue,
    RequirementIssueKind,
)
from domain.extraction_chunk import ExtractionChunk


class RequirementExtractor(Protocol):
    """Port implemented by an LLM-backed extraction adapter."""

    def extract(self, text: str, source_name: str) -> ExtractionChunk:
        """Extract structured requirements from one document fragment."""


class DocumentRequirementsService:
    """Coordinate reading, bounded chunking, extraction and result merging."""

    def __init__(
        self,
        reader: DocumentReader,
        extractor: RequirementExtractor,
        *,
        max_chars: int = 12_000,
        overlap_chars: int = 500,
        required_fields: tuple[str, ...] = (),
    ) -> None:
        if max_chars < 1:
            raise ValueError("max_chars must be positive")
        if overlap_chars < 0 or overlap_chars >= max_chars:
            raise ValueError("overlap_chars must be in [0, max_chars)")
        self._reader = reader
        self._extractor = extractor
        self._max_chars = max_chars
        self._overlap_chars = overlap_chars
        self._required_fields = required_fields

    def extract_file(self, path: Path) -> DocumentRequirements:
        text = self._reader.read_text(path)
        chunks = split_document_text(
            text,
            max_chars=self._max_chars,
            overlap_chars=self._overlap_chars,
        )
        results = [self._extractor.extract(chunk, path.name) for chunk in chunks]
        requirements = deduplicate_requirements(
            requirement for result in results for requirement in result.requirements
        )
        issues: list[RequirementIssue] = []
        if not any(result.is_relevant for result in results):
            issues.append(
                RequirementIssue(
                    kind=RequirementIssueKind.IRRELEVANT_DOCUMENT,
                    description=(
                        "The document does not appear to describe system requirements."
                    ),
                )
            )

        extracted_text = " ".join(
            f"{requirement.statement} {requirement.source_excerpt}"
            for requirement in requirements
        ).casefold()
        for field in self._required_fields:
            searchable_field = field.replace("_", " ").casefold()
            if searchable_field not in extracted_text:
                issues.append(
                    RequirementIssue(
                        kind=RequirementIssueKind.MISSING,
                        field=field,
                        description=(
                            f"Required information '{field}' was not established "
                            "by extraction."
                        ),
                    )
                )

        for result in results:
            issues.extend(
                RequirementIssue(
                    kind=RequirementIssueKind.AMBIGUOUS,
                    description=note,
                    evidence=[note],
                )
                for note in result.ambiguity_notes
            )
            issues.extend(
                RequirementIssue(
                    kind=RequirementIssueKind.CONFLICTING,
                    description=note,
                    evidence=[note],
                )
                for note in result.conflict_notes
            )

        return DocumentRequirements(
            requirements=requirements,
            issues=deduplicate_issues(issues),
            is_relevant=any(result.is_relevant for result in results),
            source_name=path.name,
        )
