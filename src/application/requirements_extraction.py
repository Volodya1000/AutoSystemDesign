"""Application service for extracting requirements from long documents."""
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from domain.document_requirements import (
    DocumentRequirements,
    Requirement,
    RequirementIssue,
    RequirementIssueKind,
)
from infrastructure.document_readers.markdown_reader import DocumentReader


class ExtractionChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirements: list[Requirement] = Field(default_factory=list)
    is_relevant: bool
    ambiguity_notes: list[str] = Field(default_factory=list)
    conflict_notes: list[str] = Field(default_factory=list)


class RequirementExtractor(Protocol):
    """Port implemented by an LLM-backed extraction agent."""

    def extract(self, text: str, source_name: str) -> ExtractionChunk: ...


class DocumentRequirementsService:
    """Coordinates reading, context-aware chunking, extraction and merging."""

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
        chunks = self._split(text)
        results = [self._extractor.extract(chunk, path.name) for chunk in chunks]
        requirements = self._deduplicate(
            requirement for result in results for requirement in result.requirements
        )
        issues: list[RequirementIssue] = []
        if not any(result.is_relevant for result in results):
            issues.append(RequirementIssue(
                kind=RequirementIssueKind.IRRELEVANT_DOCUMENT,
                description="The document does not appear to describe system requirements.",
            ))
        for field in self._required_fields:
            issues.append(RequirementIssue(
                kind=RequirementIssueKind.MISSING,
                field=field,
                description=f"Required information '{field}' was not established by extraction.",
            ))
        for result in results:
            issues.extend(RequirementIssue(
                kind=RequirementIssueKind.AMBIGUOUS,
                description=note,
            ) for note in result.ambiguity_notes)
            issues.extend(RequirementIssue(
                kind=RequirementIssueKind.CONFLICTING,
                description=note,
            ) for note in result.conflict_notes)
        return DocumentRequirements(
            requirements=requirements,
            issues=self._deduplicate_issues(issues),
            is_relevant=any(result.is_relevant for result in results),
            source_name=path.name,
        )

    def _split(self, text: str) -> list[str]:
        """Split on paragraph boundaries where possible, with bounded overlap."""
        paragraphs = [part.strip() for part in text.splitlines() if part.strip()]
        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            # Very long paragraphs are split into bounded pieces.
            pieces = [
                paragraph[i : i + self._max_chars]
                for i in range(0, len(paragraph), self._max_chars)
            ]
            for piece in pieces:
                candidate = f"{current}\n\n{piece}".strip() if current else piece
                if len(candidate) <= self._max_chars:
                    current = candidate
                    continue
                if current:
                    chunks.append(current)
                prefix = current[-self._overlap_chars:] if current and self._overlap_chars else ""
                current = f"{prefix}\n{piece}".strip() if prefix else piece
                if len(current) > self._max_chars:
                    current = current[-self._max_chars:]
        if current:
            chunks.append(current)
        return chunks or [text[: self._max_chars]]

    @staticmethod
    def _deduplicate(requirements) -> list[Requirement]:
        """Remove exact duplicates while retaining distinct evidence and wording."""
        unique: dict[tuple[str, str], Requirement] = {}
        for requirement in requirements:
            key = (requirement.kind.value, " ".join(requirement.statement.casefold().split()))
            unique.setdefault(key, requirement)
        return list(unique.values())

    @staticmethod
    def _deduplicate_issues(issues: list[RequirementIssue]) -> list[RequirementIssue]:
        unique: dict[tuple[str, str | None, str], RequirementIssue] = {}
        for issue in issues:
            key = (issue.kind.value, issue.field, issue.description.casefold().strip())
            unique.setdefault(key, issue)
        return list(unique.values())
