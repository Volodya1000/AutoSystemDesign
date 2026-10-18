"""Pure functions for document chunking and extraction-result merging."""

from application.document_processing.chunking import split_document_text
from application.document_processing.merging import (
    deduplicate_issues,
    deduplicate_requirements,
)

__all__ = [
    "deduplicate_issues",
    "deduplicate_requirements",
    "split_document_text",
]
