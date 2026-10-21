# Copyright (c) 2026 Volodya1000
"""Assertion helpers shared by document extraction unit tests."""

from collections.abc import Iterable

from domain.document_requirements import RequirementIssue, RequirementIssueKind


def has_issue(
    issues: Iterable[RequirementIssue],
    kind: RequirementIssueKind,
    *,
    description_contains: str | None = None,
    field: str | None = None,
) -> bool:
    """Return whether a matching diagnostic exists."""
    return any(
        issue.kind is kind
        and (description_contains is None or description_contains in issue.description)
        and (field is None or issue.field == field)
        for issue in issues
    )
