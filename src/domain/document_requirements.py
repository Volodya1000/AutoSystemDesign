"""Domain models for requirements extracted from source documents.

These models deliberately distinguish evidence from missing information: an
extractor must not silently turn absent requirements into invented defaults.
"""
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RequirementKind(StrEnum):
    FUNCTIONAL = "functional"
    NON_FUNCTIONAL = "non_functional"


class Requirement(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    statement: str = Field(min_length=1)
    kind: RequirementKind
    source_excerpt: str = Field(min_length=1)
    source_location: str | None = None


class RequirementIssueKind(StrEnum):
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    CONFLICTING = "conflicting"
    IRRELEVANT_DOCUMENT = "irrelevant_document"


class RequirementIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: RequirementIssueKind
    field: str | None = None
    description: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list)


class DocumentRequirements(BaseModel):
    """Validated extraction result, including completeness diagnostics."""

    model_config = ConfigDict(extra="forbid")

    requirements: list[Requirement] = Field(default_factory=list)
    issues: list[RequirementIssue] = Field(default_factory=list)
    is_relevant: bool
    source_name: str
