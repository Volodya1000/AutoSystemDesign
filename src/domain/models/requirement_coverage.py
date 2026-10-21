"""Typed evidence for checking nonfunctional requirements."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RequirementCheckStatus(StrEnum):
    """A checked requirement is not the same as a generated graph."""

    SATISFIED = "satisfied"
    VIOLATED = "violated"
    NOT_EVALUATED = "not_evaluated"


class RequirementCheckReason(StrEnum):
    """Stable explanations for missing evidence."""

    NO_VALIDATOR = "no_validator"
    MISSING_WORKLOAD = "missing_workload"
    PERCENTILE_UNMODELED = "percentile_unmodeled"
    RELIABILITY_MODEL_UNAVAILABLE = "reliability_model_unavailable"
    TARGET_SCOPE_UNSPECIFIED = "target_scope_unspecified"
    GRAPH_UNAVAILABLE = "graph_unavailable"
    GRAPH_UNACCEPTED = "graph_unaccepted"
    AMBIGUOUS_EVIDENCE = "ambiguous_evidence"
    EVIDENCE_TYPE_MISMATCH = "evidence_type_mismatch"


class RequirementAssessment(BaseModel):
    """One assessment for one occurrence in the original scenario list.

    The index-based identifier is local to the scenario, not a globally
    stable ID. Matching by type alone would collapse duplicate requirements.
    """

    model_config = ConfigDict(extra="forbid")

    requirement_identifier: str = Field(min_length=1)
    type_identifier: str = Field(min_length=1)
    status: RequirementCheckStatus
    reason: RequirementCheckReason | None = None
    validator_identifier: str | None = None

    @classmethod
    def not_evaluated(
        cls,
        *,
        identifier: str,
        kind: str,
        reason: RequirementCheckReason,
    ) -> "RequirementAssessment":
        """Explicit diagnostic for an unsupported or unavailable check."""
        return cls(
            requirement_identifier=identifier,
            type_identifier=kind,
            status=RequirementCheckStatus.NOT_EVALUATED,
            reason=reason,
        )


class RequirementCoverageStatus(StrEnum):
    """A coverage summary, separate from pipeline and generation status."""

    SATISFIED = "satisfied"
    VIOLATED = "violated"
    INCOMPLETE = "incomplete"
    NOT_APPLICABLE = "not_applicable"


class RequirementCoverageReport(BaseModel):
    """Independent artifact: does not change performance report schema v1."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    scenario_identifier: str = Field(min_length=1)
    graph_accepted: bool
    status: RequirementCoverageStatus
    requirements: list[RequirementAssessment] = Field(default_factory=list)


def requirement_identifier(index: int) -> str:
    """Address a requirement occurrence within one immutable scenario version."""
    return f"requirements[{index}]"
