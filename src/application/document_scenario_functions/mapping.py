"""Pure transformations from evidence-bearing candidates into scenario models."""

from typing import cast

from pydantic import ValidationError

from application.document_scenario_functions.evidence import resolve_candidate
from application.document_scenario_functions.naming import functional_name
from application.document_scenario_functions.results import MappingOutcome
from domain.document_requirements import RequirementIssue, RequirementIssueKind
from domain.models.functional import FunctionalRequirement
from domain.models.requirements import (
    AvailabilityRequirement,
    BudgetRequirement,
    LatencyRequirement,
    QueueSizePercentileRequirement,
    Requirement,
    ResourceUtilizationRequirement,
)
from domain.models.scenarios import WorkloadProfile
from domain.scenario_extraction import (
    EvidenceValue,
    ExtractedFunctionalRequirement,
    ExtractedMetricRequirement,
    ExtractedWorkload,
    MetricType,
)

_ALL_METRIC_FIELDS: tuple[str, ...] = (
    "threshold_value",
    "percentile",
    "minimum_value",
    "maximum_value",
)
_REQUIRED_METRIC_FIELDS: dict[MetricType, frozenset[str]] = {
    "latency": frozenset({"threshold_value", "percentile"}),
    "queue_size_percentile": frozenset({"threshold_value", "percentile"}),
    "budget": frozenset({"threshold_value"}),
    "availability": frozenset({"threshold_value"}),
    "resource_utilization": frozenset({"minimum_value", "maximum_value"}),
}


def build_workload(
    extracted: ExtractedWorkload,
    verified_excerpts: list[str],
) -> MappingOutcome[WorkloadProfile | None]:
    """Create a workload only when all fields required by the source-backed model exist."""
    candidates = (
        extracted.baseline_requests_per_second,
        extracted.peak_requests_per_second,
        extracted.read_ratio,
    )
    if not any(candidate.value is not None for candidate in candidates):
        return MappingOutcome(value=None)

    baseline = resolve_candidate(
        extracted.baseline_requests_per_second,
        "workload.baseline_requests_per_second",
        verified_excerpts,
        required=True,
        numeric=True,
    )
    peak = resolve_candidate(
        extracted.peak_requests_per_second,
        "workload.peak_requests_per_second",
        verified_excerpts,
        required=True,
        numeric=True,
    )
    read_ratio = resolve_candidate(
        extracted.read_ratio,
        "workload.read_ratio",
        verified_excerpts,
        required=False,
        numeric=True,
    )
    issues = [*baseline.issues, *peak.issues, *read_ratio.issues]
    local_evidence = dict(
        (*baseline.field_evidence, *peak.field_evidence, *read_ratio.field_evidence)
    )
    if baseline.value is None or peak.value is None:
        return MappingOutcome(value=None, issues=tuple(issues))

    if read_ratio.value is None:
        issues.append(
            RequirementIssue(
                kind=RequirementIssueKind.MISSING,
                field="workload.read_ratio",
                description=(
                    "The workload was omitted because the source-backed "
                    "read/write ratio is missing. The existing model defaults "
                    "to 0.8 if a workload is created without this field; "
                    "the extractor does not apply that assumption."
                ),
            )
        )
        return MappingOutcome(value=None, issues=tuple(issues))

    try:
        workload = WorkloadProfile(
            baseline_requests_per_second=baseline.value,
            peak_requests_per_second=peak.value,
            read_ratio=read_ratio.value,
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
        return MappingOutcome(value=None, issues=tuple(issues))

    return MappingOutcome(
        value=workload,
        issues=tuple(issues),
        field_evidence=tuple(local_evidence.items()),
    )


def build_metric_requirements(
    candidates: list[ExtractedMetricRequirement],
    verified_excerpts: list[str],
) -> MappingOutcome[list[Requirement]]:
    """Build all valid metrics while preserving diagnostics for rejected candidates."""
    output: list[ScenarioRequirement] = []
    issues: list[RequirementIssue] = []
    field_evidence: dict[str, str] = {}
    for candidate in candidates:
        result = _build_metric_requirement(
            candidate,
            len(output),
            verified_excerpts,
        )
        issues.extend(result.issues)
        if result.value is None:
            continue
        output.append(result.value)
        field_evidence.update(dict(result.field_evidence))
    return MappingOutcome(
        value=output,
        issues=tuple(issues),
        field_evidence=tuple(field_evidence.items()),
    )


def _build_metric_requirement(
    candidate: ExtractedMetricRequirement,
    index: int,
    verified_excerpts: list[str],
) -> MappingOutcome[ScenarioRequirement | None]:
    """Build one typed metric and its evidence without changing shared state."""
    base_path = f"requirements[{index}]"
    type_result = resolve_candidate(
        candidate.type_identifier,
        f"{base_path}.type_identifier",
        verified_excerpts,
        required=True,
    )
    issues = list(type_result.issues)
    if type_result.value is None:
        return MappingOutcome(value=None, issues=tuple(issues))

    metric_type = type_result.value
    required_fields = _REQUIRED_METRIC_FIELDS[metric_type]
    values: dict[str, float | None] = {}
    local_evidence: dict[str, str] = dict(type_result.field_evidence)

    for field_name in _ALL_METRIC_FIELDS:
        field_result = resolve_candidate(
            getattr(candidate, field_name),
            f"{base_path}.{field_name}",
            verified_excerpts,
            required=field_name in required_fields,
            numeric=True,
        )
        issues.extend(field_result.issues)
        values[field_name] = field_result.value
        local_evidence.update(dict(field_result.field_evidence))

    invalid_unused = False
    for field_name in _ALL_METRIC_FIELDS:
        if field_name in required_fields:
            continue
        field_candidate: EvidenceValue[float] = getattr(candidate, field_name)
        if field_candidate.value is None:
            continue
        issues.append(
            RequirementIssue(
                kind=RequirementIssueKind.INVALID_VALUE,
                field=f"{base_path}.{field_name}",
                description=(
                    f"Field '{base_path}.{field_name}' is not applicable "
                    "to this metric type."
                ),
                evidence=(
                    [field_candidate.source_excerpt]
                    if field_candidate.source_excerpt
                    else []
                ),
            )
        )
        invalid_unused = True

    if invalid_unused or any(values[name] is None for name in required_fields):
        return MappingOutcome(value=None, issues=tuple(issues))

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
        return MappingOutcome(value=None, issues=tuple(issues))

    return MappingOutcome(
        value=metric,
        issues=tuple(issues),
        field_evidence=tuple(local_evidence.items()),
    )


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


def build_functional_requirements(
    candidates: list[ExtractedFunctionalRequirement],
    verified_excerpts: list[str],
) -> MappingOutcome[list[FunctionalRequirement]]:
    """Build functional requirements whose text is verified against source evidence."""
    output: list[FunctionalRequirement] = []
    issues: list[RequirementIssue] = []
    field_evidence: dict[str, str] = {}
    for candidate in candidates:
        index = len(output)
        field_path = f"functional_requirements[{index}].text"
        result = resolve_candidate(
            candidate.text,
            field_path,
            verified_excerpts,
            required=True,
            verbatim_text=True,
        )
        issues.extend(result.issues)
        if result.value is None:
            continue

        excerpt = dict(result.field_evidence)[field_path]
        output.append(
            FunctionalRequirement(
                identifier=f"FR-{index + 1:03d}",
                name=functional_name(result.value),
                text=result.value,
            )
        )
        field_evidence[field_path] = excerpt
        field_evidence[f"functional_requirements[{index}].name"] = excerpt

    return MappingOutcome(
        value=output,
        issues=tuple(issues),
        field_evidence=tuple(field_evidence.items()),
    )
