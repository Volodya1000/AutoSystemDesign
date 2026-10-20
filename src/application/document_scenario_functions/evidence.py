"""Pure validation functions for candidate values and source evidence."""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

from application.document_processing import (
    is_evidence_supported,
    matches_verified_excerpt,
)
from application.document_scenario_functions.results import MappingOutcome
from domain.document_requirements import (
    RequirementEvidence,
    RequirementIssue,
    RequirementIssueKind,
    SourceBackedNote,
)
from domain.scenario_extraction import EvidenceValue

_NUMERIC_TOKEN = re.compile(
    r"(?<![\w.])(?P<number>[-+]?(?:\d+(?:[.,]\d+)?|[.,]\d+))"
    r"(?:st|nd|rd|th)?(?!\w)",
    re.IGNORECASE,
)


def _contains_number(text: str, expected: float) -> bool:
    """Require a numeric value to appear literally, without unit conversion."""
    if not math.isfinite(expected):
        return False
    for match in _NUMERIC_TOKEN.finditer(text):
        try:
            observed = float(match.group("number").replace(",", "."))
        except ValueError:
            continue
        if math.isclose(observed, expected, rel_tol=1e-9, abs_tol=1e-9):
            return True
    return False


@dataclass(frozen=True)
class CandidateValidationOptions:
    """Optional validation rules for a source-backed scenario field."""

    required: bool
    numeric: bool = False
    verbatim_text: bool = False


def resolve_candidate[ValueT](
    candidate: EvidenceValue[ValueT],
    field_path: str,
    verified_excerpts: Sequence[str],
    options: CandidateValidationOptions,
) -> MappingOutcome[ValueT | None]:
    """Validate a candidate without mutating caller-owned collections."""
    required = options.required
    numeric = options.numeric
    verbatim_text = options.verbatim_text
    value = candidate.value
    excerpt = candidate.source_excerpt
    if value is None:
        issues = (
            (
                RequirementIssue(
                    kind=RequirementIssueKind.MISSING,
                    field=field_path,
                    description=f"Required field '{field_path}' was not established.",
                ),
            )
            if required
            else ()
        )
        return MappingOutcome(value=None, issues=issues)

    if excerpt is None or not matches_verified_excerpt(excerpt, verified_excerpts):
        issue = RequirementIssue(
            kind=RequirementIssueKind.UNSUPPORTED_EVIDENCE,
            field=field_path,
            description=f"Scenario field '{field_path}' lacks verified evidence.",
            evidence=[excerpt] if excerpt else [],
        )
        return MappingOutcome(value=None, issues=(issue,))

    if isinstance(value, str) and not value.strip():
        issue = RequirementIssue(
            kind=RequirementIssueKind.INVALID_VALUE,
            field=field_path,
            description=f"Scenario field '{field_path}' must not be blank.",
            evidence=[excerpt],
        )
        return MappingOutcome(value=None, issues=(issue,))

    if (
        verbatim_text
        and isinstance(value, str)
        and not is_evidence_supported(
            RequirementEvidence(source_excerpt=value), excerpt
        )
    ):
        issue = RequirementIssue(
            kind=RequirementIssueKind.UNSUPPORTED_EVIDENCE,
            field=field_path,
            description=(
                f"The text for '{field_path}' is not a verbatim substring "
                "of its cited source excerpt."
            ),
            evidence=[excerpt],
        )
        return MappingOutcome(value=None, issues=(issue,))

    if numeric and (
        not isinstance(value, (int, float))
        or not _contains_number(excerpt, float(value))
    ):
        issue = RequirementIssue(
            kind=RequirementIssueKind.UNSUPPORTED_EVIDENCE,
            field=field_path,
            description=(
                f"The cited excerpt does not contain the literal numeric value "
                f"for '{field_path}'. Unit conversion and "
                "inferred values are not allowed."
            ),
            evidence=[excerpt],
        )
        return MappingOutcome(value=None, issues=(issue,))

    return MappingOutcome(
        value=value,
        field_evidence=((field_path, excerpt),),
    )


def validate_source_backed_notes(
    notes: Sequence[SourceBackedNote],
    verified_excerpts: Sequence[str],
    issue_kind: RequirementIssueKind,
) -> tuple[RequirementIssue, ...]:
    """Convert source-backed notes into diagnostics only when their citations verify."""
    issues: list[RequirementIssue] = []
    for note in notes:
        excerpts = [evidence.source_excerpt for evidence in note.source_evidence]
        unsupported = [
            excerpt
            for excerpt in excerpts
            if not matches_verified_excerpt(excerpt, verified_excerpts)
        ]
        description_supported = any(
            is_evidence_supported(
                RequirementEvidence(source_excerpt=note.description), excerpt
            )
            for excerpt in excerpts
        )
        # A conflict can be a relation between separate statements, so its
        # explanation need not be a substring of either statement. Requiring
        # multiple independently verified citations keeps this exception narrow.
        synthesized_conflict_supported = (
            issue_kind is RequirementIssueKind.CONFLICTING
            and len({" ".join(excerpt.split()) for excerpt in excerpts}) >= MIN_AND_JOIN_EXCERPT_SPLIT_COUNT_FOR_EXCERPT
        )
        if unsupported or not (description_supported or synthesized_conflict_supported):
            issues.append(
                RequirementIssue(
                    kind=RequirementIssueKind.UNSUPPORTED_EVIDENCE,
                    description=(
                        "Discarded scenario note because its citation or "
                        f"description is unsupported: {note.description}"
                    ),
                    evidence=unsupported or excerpts,
                )
            )
            continue
        issues.append(
            RequirementIssue(
                kind=issue_kind,
                description=note.description,
                evidence=excerpts,
            )
        )
    return tuple(issues)

MIN_AND_JOIN_EXCERPT_SPLIT_COUNT_FOR_EXCERPT = 2

