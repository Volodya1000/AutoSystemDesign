"""Structured, evidence-bearing DTOs for mapping requirements to a scenario."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from domain.document_requirements import RequirementIssue, SourceBackedNote
from domain.models.scenarios import DesignScenario


class EvidencePairValidationError(ValueError):
    """Evidence value and citation are inconsistent."""


class EvidenceValue[ValueT](BaseModel):
    """A candidate field value paired with a source citation or two nulls."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    value: ValueT | None
    source_excerpt: str | None

    @model_validator(mode="after")
    def _validate_evidence_pair(self) -> Self:
        if (self.value is None) != (self.source_excerpt is None):
            raise EvidencePairValidationError(
                "value and source_excerpt must both be set or both be null"
            )
        if self.source_excerpt is not None and not self.source_excerpt.strip():
            raise EvidencePairValidationError("source_excerpt must not be blank")
        return self


class ExtractedWorkload(BaseModel):
    """Field-level candidates for the scenario's traffic profile."""

    model_config = ConfigDict(extra="forbid")

    baseline_requests_per_second: EvidenceValue[float]
    peak_requests_per_second: EvidenceValue[float]
    read_ratio: EvidenceValue[float]


MetricType = Literal[
    "latency",
    "queue_size_percentile",
    "budget",
    "availability",
    "resource_utilization",
]


class ExtractedMetricRequirement(BaseModel):
    """Evidence-bearing candidate for one supported non-functional requirement."""

    model_config = ConfigDict(extra="forbid")

    type_identifier: EvidenceValue[MetricType]
    threshold_value: EvidenceValue[float]
    percentile: EvidenceValue[float]
    minimum_value: EvidenceValue[float]
    maximum_value: EvidenceValue[float]


class ExtractedFunctionalRequirement(BaseModel):
    """A functional requirement's assertion with source evidence."""

    model_config = ConfigDict(extra="forbid")

    text: EvidenceValue[str]


class DocumentScenarioExtraction(BaseModel):
    """LLM output DTO; all scenario fields must carry explicit evidence wrappers."""

    model_config = ConfigDict(extra="forbid")

    description: EvidenceValue[str]
    workload: ExtractedWorkload
    requirements: list[ExtractedMetricRequirement]
    functional_requirements: list[ExtractedFunctionalRequirement]
    is_relevant: bool
    ambiguity_notes: list[SourceBackedNote]
    conflict_notes: list[SourceBackedNote]


class DocumentScenarioResult(BaseModel):
    """Validated scenario candidate and evidence manifest for human review."""

    model_config = ConfigDict(extra="forbid")

    scenario: DesignScenario | None
    field_evidence: dict[str, str]
    issues: list[RequirementIssue]
    is_relevant: bool
    source_name: str
