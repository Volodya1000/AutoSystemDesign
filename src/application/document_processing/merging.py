"""Pure deduplication functions for extracted requirements and diagnostics."""

from collections.abc import Iterable

from domain.document_requirements import Requirement, RequirementIssue


def deduplicate_requirements(
    requirements: Iterable[Requirement],
) -> list[Requirement]:
    """Keep the first requirement for each kind and normalized statement."""
    unique: dict[tuple[str, str], Requirement] = {}
    for requirement in requirements:
        normalized_statement = " ".join(requirement.statement.casefold().split())
        key = (requirement.kind.value, normalized_statement)
        unique.setdefault(key, requirement)
    return list(unique.values())


def deduplicate_issues(issues: Iterable[RequirementIssue]) -> list[RequirementIssue]:
    """Keep the first issue for each kind, field and normalized description."""
    unique: dict[tuple[str, str | None, str], RequirementIssue] = {}
    for issue in issues:
        normalized_description = " ".join(issue.description.casefold().split())
        key = (issue.kind.value, issue.field, normalized_description)
        unique.setdefault(key, issue)
    return list(unique.values())
