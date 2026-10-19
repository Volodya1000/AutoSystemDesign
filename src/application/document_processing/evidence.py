"""Pure helpers for validating verbatim citations against source fragments."""

from domain.document_requirements import RequirementEvidence


def normalize_whitespace(text: str) -> str:
    """Collapse whitespace while preserving case and punctuation."""
    return " ".join(text.split())


def is_evidence_supported(evidence: RequirementEvidence, source_text: str) -> bool:
    """Return whether a citation occurs verbatim, ignoring whitespace differences."""
    excerpt = normalize_whitespace(evidence.source_excerpt)
    normalized_source = normalize_whitespace(source_text)
    return bool(excerpt) and excerpt in normalized_source
