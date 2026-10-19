"""Pure functions for document chunking, evidence validation and merging."""

from application.document_processing.chunking import split_document_text
from application.document_processing.evidence import is_evidence_supported
from application.document_processing.merging import (
    deduplicate_issues,
    deduplicate_requirements,
)

__all__ = [
    "deduplicate_issues",
    "deduplicate_requirements",
    "is_evidence_supported",
    "split_document_text",
]
