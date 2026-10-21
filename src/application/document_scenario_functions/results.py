# Copyright (c) 2026 Volodya1000
"""Immutable results returned by pure scenario-mapping functions."""

from dataclasses import dataclass

from domain.document_requirements import RequirementIssue


@dataclass(frozen=True, slots=True)
class MappingOutcome[ValueT]:
    """A transformation value plus diagnostics and source evidence it established."""

    value: ValueT
    issues: tuple[RequirementIssue, ...] = ()
    field_evidence: tuple[tuple[str, str], ...] = ()
