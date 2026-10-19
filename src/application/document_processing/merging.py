"""Pure deduplication functions for extracted requirements and diagnostics."""

from collections.abc import Iterable

from domain.document_requirements import (
    Requirement,
    RequirementEvidence,
    RequirementIssue,
)


def deduplicate_requirements(
    requirements: Iterable[Requirement],
) -> list[Requirement]:
    """Merge duplicate claims without discarding their source citations."""
    unique: dict[tuple[str, str], Requirement] = {}
    for requirement in requirements:
        normalized_statement = " ".join(requirement.statement.casefold().split())
        key = (requirement.kind.value, normalized_statement)
        existing = unique.get(key)
        if existing is None:
            unique[key] = requirement
            continue

        evidence_by_key: dict[tuple[str, str | None], RequirementEvidence] = {
            (
                " ".join(evidence.source_excerpt.split()),
                evidence.source_location,
            ): evidence
            for evidence in existing.source_evidence
        }
        for evidence in requirement.source_evidence:
            evidence_key = (
                " ".join(evidence.source_excerpt.split()),
                evidence.source_location,
            )
            evidence_by_key.setdefault(evidence_key, evidence)
        unique[key] = Requirement(
            statement=existing.statement,
            kind=existing.kind,
            source_evidence=list(evidence_by_key.values()),
        )
    return list(unique.values())


def deduplicate_issues(issues: Iterable[RequirementIssue]) -> list[RequirementIssue]:
    """Keep the first issue for each kind, field and normalized description."""
    unique: dict[tuple[str, str | None, str], RequirementIssue] = {}
    for issue in issues:
        normalized_description = " ".join(issue.description.casefold().split())
        key = (issue.kind.value, issue.field, normalized_description)
        unique.setdefault(key, issue)
    return list(unique.values())
