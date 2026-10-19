"""Application service for converting grounded claims into pipeline scenarios."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Protocol, TypeVar, cast

from pydantic import ValidationError

from application.document_processing import deduplicate_issues, is_evidence_supported
from application.requirements_extraction import DocumentRequirementsService
from domain.document_requirements import (
    DocumentRequirements,
    RequirementEvidence,
    RequirementIssue,
    RequirementIssueKind,
    SourceBackedNote,
)
from domain.models.functional import FunctionalRequirement
from domain.models.requirements import (
    AvailabilityRequirement,
    BudgetRequirement,
    LatencyRequirement,
    QueueSizePercentileRequirement,
    Requirement as ScenarioRequirement,
    ResourceUtilizationRequirement,
)
from domain.models.scenarios import DesignScenario, WorkloadProfile
from domain.scenario_extraction import (
    DocumentScenarioExtraction,
    DocumentScenarioResult,
    EvidenceValue,
    ExtractedMetricRequirement,
    ExtractedWorkload,
    MetricType,
)


class DocumentScenarioMapper(Protocol):
    """Port implemented by the LLM adapter that proposes evidence-bearing fields."""

    def map(self, requirements: DocumentRequirements) -> DocumentScenarioExtraction:
        """Map verified requirement claims into candidate scenario values."""


ValueT = TypeVar("ValueT")
_ALL_METRIC_FIELDS = (
    "threshold_value",
    "percentile",
    "minimum_value",
    "maximum_value",
)
_REQUIRED_METRIC_FIELDS: dict[MetricType, set[str]] = {
    "latency": {"threshold_value", "percentile"},
    "queue_size_percentile": {"threshold_value", "percentile"},
    "budget": {"threshold_value"},
    "availability": {"threshold_value"},
    "resource_utilization": {"minimum_value", "maximum_value"},
}
_NUMERIC_TOKEN = re.compile(
    r"(?<![\w.])(?P<number>[-+]?(?:\d+(?:[.,]\d+)?|[.,]\d+))"
    r"(?:st|nd|rd|th)?(?!\w)",
    re.IGNORECASE,
)


def _contains_number(text: str, expected: float) -> bool:
    """Require a numeric value to appear literally, without unit conversion."""
    if not math.isfinite(expected):
        return False
    for match in _NUMERIC_TOKEN.finditer(text):
        try:
            observed = float(match.group("number").replace(",", "."))
        except ValueError:
            continue
        if math.isclose(observed, expected, rel_tol=1e-9, abs_tol=1e-9):
            return True
    return False


def _resolve_candidate(
    candidate: EvidenceValue[ValueT],
    field_path: str,
    verified_excerpts: list[str],
    issues: list[RequirementIssue],
    field_evidence: dict[str, str],
    *,
    required: bool,
    numeric: bool = False,
    verbatim_text: bool = False,
) -> ValueT | None:
    """Validate candidate provenance and, for numbers, its literal value."""
    value = candidate.value
    excerpt = candidate.source_excerpt
    if value is None:
        if required:
            issues.append(
                RequirementIssue(
                    kind=RequirementIssueKind.MISSING,
                    field=field_path,
                    description=f"Required scenario field '{field_path}' was not established.",
                )
            )
        return None

    if excerpt is None or not any(
        is_evidence_supported(RequirementEvidence(source_excerpt=excerpt), source_excerpt)
        for source_excerpt in verified_excerpts
    ):
        issues.append(
            RequirementIssue(
                kind=RequirementIssueKind.UNSUPPORTED_EVIDENCE,
                field=field_path,
                description=f"Scenario field '{field_path}' cites no verified source excerpt.",
                evidence=[excerpt] if excerpt else [],
            )
        )
        return None

    if isinstance(value, str) and not value.strip():
        issues.append(
            RequirementIssue(
                kind=RequirementIssueKind.INVALID_VALUE,
                field=field_path,
                description=f"Scenario field '{field_path}' must not be blank.",
                evidence=[excerpt],
            )
        )
        return None

    if verbatim_text and isinstance(value, str) and not is_evidence_supported(
        RequirementEvidence(source_excerpt=value), excerpt
    ):
        issues.append(
            RequirementIssue(
                kind=RequirementIssueKind.UNSUPPORTED_EVIDENCE,
                field=field_path,
                description=(
                    f"The text for '{field_path}' is not a verbatim substring "
                    "of its cited source excerpt."
                ),
                evidence=[excerpt],
            )
        )
        return None

    if numeric and (
        not isinstance(value, (int, float))
        or not _contains_number(excerpt, float(value))
    ):
        issues.append(
            RequirementIssue(
                kind=RequirementIssueKind.UNSUPPORTED_EVIDENCE,
                field=field_path,
                description=(
                    f"The cited excerpt does not contain the literal numeric value "
                    f"for '{field_path}'. Unit conversion and inferred values are not allowed."
                ),
                evidence=[excerpt],
            )
        )
        return None

    field_evidence[field_path] = excerpt
    return value


def _reject_unexpected_value(
    candidate: EvidenceValue[float],
    field_path: str,
    issues: list[RequirementIssue],
) -> bool:
    """Ensure a metric does not populate fields that its type cannot represent."""
    if candidate.value is None:
        return False
    issues.append(
        RequirementIssue(
            kind=RequirementIssueKind.INVALID_VALUE,
            field=field_path,
            description=f"Field '{field_path}' is not applicable to this metric type.",
            evidence=[candidate.source_excerpt] if candidate.source_excerpt else [],
        )
    )
    return True


def _slug_identifier(source_name: str) -> str:
    """Build a deterministic YAML-safe identifier from the source filename."""
    stem = source_name.rsplit(".", maxsplit=1)[0]
    identifier = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_-")[:64]
    if not identifier:
        return "document"
    if not identifier[0].isalnum() or not identifier[0].isascii():
        return f"doc_{identifier}"[:64]
    return identifier


def _functional_name(text: str) -> str:
    """Derive a readable functional-requirement name without another LLM call."""
    first_sentence = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0]
    return first_sentence[:80].rstrip()


class DocumentScenarioService:
    """Build a canonical scenario only from candidates with verifiable citations."""

    def __init__(
        self,
        requirements_service: DocumentRequirementsService,
        mapper: DocumentScenarioMapper,
    ) -> None:
        self._requirements_service = requirements_service
        self._mapper = mapper

    def extract_file(self, path: Path) -> DocumentScenarioResult:
        """Read a Markdown document and map its verified claims to a scenario."""
        requirements = self._requirements_service.extract_file(path)
        return self.map_requirements(requirements)

    def map_requirements(
        self, requirements: DocumentRequirements
    ) -> DocumentScenarioResult:
        """Map a pre-extracted result; useful for deterministic unit tests."""
        issues: list[RequirementIssue] = list(requirements.issues)
        verified_excerpts = [
            evidence.source_excerpt
            for requirement in requirements.requirements
            for evidence in requirement.source_evidence
        ]
        if not requirements.is_relevant or not requirements.requirements:
            if requirements.is_relevant and not requirements.requirements:
                issues.append(
                    RequirementIssue(
                        kind=RequirementIssueKind.UNSUPPORTED_EVIDENCE,
                        description=(
                            "No source-grounded requirements remain after evidence validation."
                        ),
                    )
                )
            return DocumentScenarioResult(
                scenario=None,
                field_evidence={},
                issues=deduplicate_issues(issues),
                is_relevant=requirements.is_relevant,
                source_name=requirements.source_name,
            )

        extraction = self._mapper.map(requirements)
        self._append_backed_notes(
            extraction.ambiguity_notes,
            verified_excerpts,
            issues,
            RequirementIssueKind.AMBIGUOUS,
        )
        self._append_backed_notes(
            extraction.conflict_notes,
            verified_excerpts,
            issues,
            RequirementIssueKind.CONFLICTING,
        )
        if not extraction.is_relevant:
            issues.append(
                RequirementIssue(
                    kind=RequirementIssueKind.IRRELEVANT_DOCUMENT,
                    description="Scenario mapping marked the source as irrelevant.",
                )
            )
            return DocumentScenarioResult(
                scenario=None,
                field_evidence={},
                issues=deduplicate_issues(issues),
                is_relevant=False,
                source_name=requirements.source_name,
            )

        field_evidence: dict[str, str] = {}
        description = _resolve_candidate(
            extraction.description,
            "description",
            verified_excerpts,
            issues,
            field_evidence,
            required=True,
            verbatim_text=True,
        )

        workload = self._build_workload(
            extraction.workload,
            verified_excerpts,
            issues,
            field_evidence,
        )
        scenario_requirements = self._build_metric_requirements(
            extraction.requirements,
            verified_excerpts,
            issues,
            field_evidence,
        )
        functional_requirements = self._build_functional_requirements(
            extraction,
            verified_excerpts,
            issues,
            field_evidence,
        )

        scenario: DesignScenario | None = None
        if description is not None:
            try:
                scenario = DesignScenario(
                    identifier=_slug_identifier(requirements.source_name),
                    description=description,
                    workload=workload,
                    requirements=scenario_requirements,
                    functional_requirements=functional_requirements,
                )
            except ValidationError as error:
                issues.append(
                    RequirementIssue(
                        kind=RequirementIssueKind.INVALID_VALUE,
                        field="scenario",
                        description=f"Mapped values violate the scenario schema: {error}",
                    )
                )

        return DocumentScenarioResult(
            scenario=scenario,
            field_evidence=field_evidence,
            issues=deduplicate_issues(issues),
            is_relevant=True,
            source_name=requirements.source_name,
        )

    @staticmethod
    def _append_backed_notes(
        notes: list[SourceBackedNote],
        verified_excerpts: list[str],
        issues: list[RequirementIssue],
        issue_kind: RequirementIssueKind,
    ) -> None:
        for note in notes:
            excerpts = [evidence.source_excerpt for evidence in note.source_evidence]
            unsupported = [
                excerpt
                for excerpt in excerpts
                if not any(
                    is_evidence_supported(
                        RequirementEvidence(source_excerpt=excerpt), verified
                    )
                    for verified in verified_excerpts
                )
            ]
            if unsupported:
                issues.append(
                    RequirementIssue(
                        kind=RequirementIssueKind.UNSUPPORTED_EVIDENCE,
                        description=(
                            "Discarded scenario note with unsupported evidence: "
                            f"{note.description}"
                        ),
                        evidence=unsupported,
                    )
                )
                continue
            issues.append(
                RequirementIssue(
                    kind=issue_kind,
                    description=note.description,
                    evidence=excerpts,
                )
            )

    @staticmethod
    def _build_workload(
        extracted: ExtractedWorkload,
        verified_excerpts: list[str],
        issues: list[RequirementIssue],
        field_evidence: dict[str, str],
    ) -> WorkloadProfile | None:
        baseline_candidate = extracted.baseline_requests_per_second
        peak_candidate = extracted.peak_requests_per_second
        read_ratio_candidate = extracted.read_ratio
        workload_requested = any(
            candidate.value is not None
            for candidate in (baseline_candidate, peak_candidate, read_ratio_candidate)
        )
        if not workload_requested:
            return None

        local_evidence: dict[str, str] = {}
        baseline = _resolve_candidate(
            baseline_candidate,
            "workload.baseline_requests_per_second",
            verified_excerpts,
            issues,
            local_evidence,
            required=True,
            numeric=True,
        )
        peak = _resolve_candidate(
            peak_candidate,
            "workload.peak_requests_per_second",
            verified_excerpts,
            issues,
            local_evidence,
            required=True,
            numeric=True,
        )
        read_ratio = _resolve_candidate(
            read_ratio_candidate,
            "workload.read_ratio",
            verified_excerpts,
            issues,
            local_evidence,
            required=False,
            numeric=True,
        )
        if baseline is None or peak is None:
            return None

        if read_ratio is None:
            issues.append(
                RequirementIssue(
                    kind=RequirementIssueKind.MISSING,
                    field="workload.read_ratio",
                    description=(
                        "Read/write ratio is not source-backed. The existing "
                        "WorkloadProfile default of 0.8 will apply when this YAML "
                        "is loaded; confirm it or add an explicit ratio."
                    ),
                )
            )
        try:
            workload = WorkloadProfile(
                baseline_requests_per_second=baseline,
                peak_requests_per_second=peak,
                **({"read_ratio": read_ratio} if read_ratio is not None else {}),
            )
        except ValidationError as error:
            issues.append(
                RequirementIssue(
                    kind=RequirementIssueKind.INVALID_VALUE,
                    field="workload",
                    description=f"Mapped workload violates its schema: {error}",
                    evidence=list(local_evidence.values()),
                )
            )
            return None
        field_evidence.update(local_evidence)
        return workload

    @staticmethod
    def _build_metric_requirements(
        candidates: list[ExtractedMetricRequirement],
        verified_excerpts: list[str],
        issues: list[RequirementIssue],
        field_evidence: dict[str, str],
    ) -> list[ScenarioRequirement]:
        output: list[ScenarioRequirement] = []
        for candidate in candidates:
            base_path = f"requirements[{len(output)}]"
            local_evidence: dict[str, str] = {}
            metric_type = _resolve_candidate(
                candidate.type_identifier,
                f"{base_path}.type_identifier",
                verified_excerpts,
                issues,
                local_evidence,
                required=True,
            )
            if metric_type is None:
                continue

            required_fields = _REQUIRED_METRIC_FIELDS[metric_type]
            values: dict[str, float | None] = {}
            for field_name in _ALL_METRIC_FIELDS:
                values[field_name] = _resolve_candidate(
                    getattr(candidate, field_name),
                    f"{base_path}.{field_name}",
                    verified_excerpts,
                    issues,
                    local_evidence,
                    required=field_name in required_fields,
                    numeric=True,
                )

            invalid_unused = False
            for field_name in _ALL_METRIC_FIELDS:
                if field_name not in required_fields:
                    rejected = _reject_unexpected_value(
                        getattr(candidate, field_name),
                        f"{base_path}.{field_name}",
                        issues,
                    )
                    invalid_unused = rejected or invalid_unused
            if invalid_unused or any(values[name] is None for name in required_fields):
                continue

            try:
                metric = _create_metric(metric_type, values)
            except ValidationError as error:
                issues.append(
                    RequirementIssue(
                        kind=RequirementIssueKind.INVALID_VALUE,
                        field=base_path,
                        description=f"Mapped metric violates its schema: {error}",
                        evidence=list(local_evidence.values()),
                    )
                )
                continue
            output.append(metric)
            field_evidence.update(local_evidence)
        return output


def _create_metric(
    metric_type: MetricType,
    values: dict[str, float | None],
) -> ScenarioRequirement:
    """Instantiate the canonical non-functional model after field validation."""
    match metric_type:
        case "latency":
            return LatencyRequirement(
                threshold_value=cast(float, values["threshold_value"]),
                percentile=cast(float, values["percentile"]),
            )
        case "queue_size_percentile":
            return QueueSizePercentileRequirement(
                threshold_value=cast(float, values["threshold_value"]),
                percentile=cast(float, values["percentile"]),
            )
        case "budget":
            return BudgetRequirement(
                threshold_value=cast(float, values["threshold_value"]),
            )
        case "availability":
            return AvailabilityRequirement(
                threshold_value=cast(float, values["threshold_value"]),
            )
        case "resource_utilization":
            return ResourceUtilizationRequirement(
                minimum_value=cast(float, values["minimum_value"]),
                maximum_value=cast(float, values["maximum_value"]),
            )
        case _:
            raise AssertionError(f"Unsupported metric type: {metric_type}")
    @staticmethod
    def _build_functional_requirements(
        extraction: DocumentScenarioExtraction,
        verified_excerpts: list[str],
        issues: list[RequirementIssue],
        field_evidence: dict[str, str],
    ) -> list[FunctionalRequirement]:
        output: list[FunctionalRequirement] = []
        for candidate in extraction.functional_requirements:
            index = len(output)
            field_path = f"functional_requirements[{index}].text"
            text = _resolve_candidate(
                candidate.text,
                field_path,
                verified_excerpts,
                issues,
                field_evidence,
                required=True,
                verbatim_text=True,
            )
            if text is None:
                continue
            output.append(
                FunctionalRequirement(
                    identifier=f"FR-{index + 1:03d}",
                    name=_functional_name(text),
                    text=text,
                )
            )
            excerpt = field_evidence[field_path]
            field_evidence[f"functional_requirements[{index}].name"] = excerpt
        return output
