# Copyright (c) 2026 Volodya1000
"""Validated output model for one document-fragment extraction."""

from pydantic import BaseModel, ConfigDict

from domain.document_requirements import Requirement, SourceBackedNote


class ExtractionChunk(BaseModel):
    """Structured, source-grounded extraction result for one fragment."""

    model_config = ConfigDict(extra="forbid")

    requirements: list[Requirement]
    is_relevant: bool
    ambiguity_notes: list[SourceBackedNote]
    conflict_notes: list[SourceBackedNote]
