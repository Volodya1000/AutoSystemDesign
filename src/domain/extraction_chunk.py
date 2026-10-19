"""Validated output model for one document-fragment extraction."""

from pydantic import BaseModel, ConfigDict, Field

from domain.document_requirements import Requirement


class ExtractionChunk(BaseModel):
    """Structured, source-grounded extraction result for one fragment."""

    model_config = ConfigDict(extra="forbid")

    requirements: list[Requirement]
    is_relevant: bool
    ambiguity_notes: list[str]
    conflict_notes: list[str]
