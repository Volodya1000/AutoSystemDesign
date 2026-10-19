"""Pure helpers for validating source citations against source text."""

from collections.abc import Iterable

from domain.document_requirements import RequirementEvidence


def normalize_whitespace(text: str) -> str:
    """Collapse whitespace while preserving case and punctuation."""
    return " ".join(text.split())


def is_evidence_supported(evidence: RequirementEvidence, source_text: str) -> bool:
    """Return whether a citation occurs in source, ignoring whitespace differences."""
    excerpt = normalize_whitespace(evidence.source_excerpt)
    normalized_source = normalize_whitespace(source_text)
    return bool(excerpt) and excerpt in normalized_source


def matches_verified_excerpt(excerpt: str, verified_excerpts: Iterable[str]) -> bool:
    """Require a scenario-field citation to match a complete verified excerpt."""
    normalized_excerpt = normalize_whitespace(excerpt)
    return bool(normalized_excerpt) and any(
        normalize_whitespace(verified) == normalized_excerpt
        for verified in verified_excerpts
    )
