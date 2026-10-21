# Copyright (c) 2026 Volodya1000
"""Pure helpers for document chunking, citation validation and merging."""

from application.document_processing.chunking import split_document_text
from application.document_processing.evidence import (
    is_evidence_supported,
    matches_verified_excerpt,
)
from application.document_processing.merging import (
    deduplicate_issues,
    deduplicate_requirements,
)

__all__ = [
    "deduplicate_issues",
    "deduplicate_requirements",
    "is_evidence_supported",
    "matches_verified_excerpt",
    "split_document_text",
]
