"""Pure deduplication functions for extracted requirements and diagnostics."""

from collections.abc import Iterable
from typing import NamedTuple

from domain.document_requirements import (
    Requirement,
    RequirementEvidence,
    RequirementIssue,
)


class RequirementKey(NamedTuple):
    """Named dictionary key for semantically identical requirement claims."""

    kind: str
    normalized_statement: str


class RequirementIssueKey(NamedTuple):
    """Named dictionary key for equivalent diagnostic issues."""

    kind: str
    field: str | None
    normalized_description: str


def deduplicate_requirements(
    requirements: Iterable[Requirement],
) -> list[Requirement]:
    """Merge duplicate claims without discarding their source citations."""
    unique: dict[RequirementKey, Requirement] = {}
    for requirement in requirements:
        normalized_statement = " ".join(requirement.statement.casefold().split())
        key = RequirementKey(requirement.kind.value, normalized_statement)
        existing = unique.get(key)
        if existing is None:
            unique[key] = requirement
            continue

        evidence_by_key: dict[str, RequirementEvidence] = {
            " ".join(evidence.source_excerpt.split()): evidence
            for evidence in existing.source_evidence
        }
        for evidence in requirement.source_evidence:
            evidence_key = " ".join(evidence.source_excerpt.split())
            evidence_by_key.setdefault(evidence_key, evidence)
        unique[key] = Requirement(
            statement=existing.statement,
            kind=existing.kind,
            source_evidence=list(evidence_by_key.values()),
        )
    return list(unique.values())


def deduplicate_issues(issues: Iterable[RequirementIssue]) -> list[RequirementIssue]:
    """Merge duplicate diagnostics while preserving every distinct evidence item."""
    unique: dict[RequirementIssueKey, RequirementIssue] = {}
    for issue in issues:
        normalized_description = " ".join(issue.description.casefold().split())
        key = RequirementIssueKey(
            issue.kind.value,
            issue.field,
            normalized_description,
        )
        existing = unique.get(key)
        if existing is None:
            unique[key] = issue
            continue
        existing_evidence = dict.fromkeys(existing.evidence)
        existing_evidence.update(dict.fromkeys(issue.evidence))
        unique[key] = RequirementIssue(
            kind=existing.kind,
            field=existing.field,
            description=existing.description,
            evidence=list(existing_evidence),
        )
    return list(unique.values())
