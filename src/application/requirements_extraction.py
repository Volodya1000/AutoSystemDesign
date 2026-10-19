"""Application service coordinating document reading and requirement extraction."""

from pathlib import Path
from typing import Protocol

from application.document_processing import (
    deduplicate_issues,
    deduplicate_requirements,
    is_evidence_supported,
    matches_verified_excerpt,
    split_document_text,
)
from application.document_reader import DocumentInputError, DocumentReader
from domain.document_requirements import (
    DocumentRequirements,
    Requirement,
    RequirementEvidence,
    RequirementIssue,
    RequirementIssueKind,
    SourceBackedNote,
)
from domain.extraction_chunk import ExtractionChunk


class RequirementExtractor(Protocol):
    """Port implemented by an LLM-backed extraction adapter."""

    def extract(self, text: str, source_name: str) -> ExtractionChunk:
        """Extract structured requirements from one document fragment."""


class DocumentRequirementsService:
    """Coordinate reading, bounded chunking, evidence validation and merging."""

    def __init__(
        self,
        reader: DocumentReader,
        extractor: RequirementExtractor,
        *,
        max_chars: int = 12_000,
        overlap_chars: int = 500,
    ) -> None:
        if max_chars < 1:
            raise DocumentInputError("max_chars must be positive")
        if overlap_chars < 0 or overlap_chars >= max_chars:
            raise DocumentInputError("overlap_chars must be in [0, max_chars)")
        self._reader = reader
        self._extractor = extractor
        self._max_chars = max_chars
        self._overlap_chars = overlap_chars

    def extract_file(self, path: Path) -> DocumentRequirements:
        return self.extract_text(self._reader.read_text(path), path.name)

    def extract_text(self, text: str, source_name: str) -> DocumentRequirements:
        """Extract requirements from already-read text without rereading the file."""
        chunks = split_document_text(
            text,
            max_chars=self._max_chars,
            overlap_chars=self._overlap_chars,
        )
        results = [self._extractor.extract(chunk, source_name) for chunk in chunks]
        requirements: list[Requirement] = []
        issues: list[RequirementIssue] = []

        for chunk, result in zip(chunks, results, strict=True):
            for requirement in result.requirements:
                verified: list[RequirementEvidence] = []
                unsupported: list[RequirementEvidence] = []
                for evidence in requirement.source_evidence:
                    if is_evidence_supported(evidence, chunk):
                        verified.append(evidence)
                    else:
                        unsupported.append(evidence)

                if unsupported:
                    issues.append(
                        RequirementIssue(
                            kind=RequirementIssueKind.UNSUPPORTED_EVIDENCE,
                            description=(
                                "One or more citations were not found in source text "
                                f"for requirement: {requirement.statement}"
                            ),
                            evidence=[
                                f"Unverified citation: {evidence.source_excerpt}"
                                for evidence in unsupported
                            ],
                        )
                    )
                claim_evidence = [
                    evidence
                    for evidence in verified
                    if matches_verified_excerpt(
                        requirement.statement, [evidence.source_excerpt]
                    )
                ]
                if verified and not claim_evidence:
                    issues.append(
                        RequirementIssue(
                            kind=RequirementIssueKind.UNSUPPORTED_EVIDENCE,
                            description=(
                                "The requirement statement does not exactly match a "
                                f"verified source excerpt: {requirement.statement}"
                            ),
                            evidence=[evidence.source_excerpt for evidence in verified],
                        )
                    )
                if claim_evidence:
                    requirements.append(
                        Requirement(
                            statement=requirement.statement,
                            kind=requirement.kind,
                            source_evidence=claim_evidence,
                        )
                    )

            issues.extend(
                self._note_issue(
                    note,
                    chunk,
                    RequirementIssueKind.AMBIGUOUS,
                    "ambiguity note",
                )
                for note in result.ambiguity_notes
            )
            issues.extend(
                self._note_issue(
                    note,
                    chunk,
                    RequirementIssueKind.CONFLICTING,
                    "conflict note",
                )
                for note in result.conflict_notes
            )

        if not any(result.is_relevant for result in results):
            issues.append(
                RequirementIssue(
                    kind=RequirementIssueKind.IRRELEVANT_DOCUMENT,
                    description=(
                        "The document does not appear to describe system requirements."
                    ),
                )
            )

        return DocumentRequirements(
            requirements=deduplicate_requirements(requirements),
            issues=deduplicate_issues(issues),
            is_relevant=any(result.is_relevant for result in results),
            source_name=source_name,
        )

    @staticmethod
    def _note_issue(
        note: SourceBackedNote,
        chunk: str,
        issue_kind: RequirementIssueKind,
        note_label: str,
    ) -> RequirementIssue:
        unsupported = [
            evidence.source_excerpt
            for evidence in note.source_evidence
            if not is_evidence_supported(evidence, chunk)
        ]
        if unsupported:
            return RequirementIssue(
                kind=RequirementIssueKind.UNSUPPORTED_EVIDENCE,
                description=(
                    f"Discarded {note_label} with unsupported citations: "
                    f"{note.description}"
                ),
                evidence=[f"Unverified citation: {excerpt}" for excerpt in unsupported],
            )

        if not any(
            is_evidence_supported(
                RequirementEvidence(source_excerpt=note.description),
                evidence.source_excerpt,
            )
            for evidence in note.source_evidence
        ):
            return RequirementIssue(
                kind=RequirementIssueKind.UNSUPPORTED_EVIDENCE,
                description=(
                    f"Discarded {note_label} whose description is not a verbatim "
                    f"substring of its citations: {note.description}"
                ),
                evidence=[evidence.source_excerpt for evidence in note.source_evidence],
            )

        return RequirementIssue(
            kind=issue_kind,
            description=note.description,
            evidence=[evidence.source_excerpt for evidence in note.source_evidence],
        )
