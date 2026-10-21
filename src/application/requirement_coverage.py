"""Build an NFR coverage report only from typed, recorded evidence."""

from domain.models.requirement_coverage import (
    RequirementAssessment,
    RequirementCheckReason,
    RequirementCheckStatus,
    RequirementCoverageReport,
    RequirementCoverageStatus,
    requirement_identifier,
)
from domain.models.scenarios import DesignScenario
from domain.specifications.interfaces import ValidationResult


def _resolve_assessment(
    identifier: str,
    kind: str,
    matches: list[RequirementAssessment],
    *,
    graph_accepted: bool,
    validation_available: bool,
) -> RequirementAssessment:
    """Reject missing, conflicting, or unrelated validation evidence."""
    if len(matches) != 1 or matches[0].type_identifier != kind:
        reason: RequirementCheckReason = RequirementCheckReason.NO_VALIDATOR
        if not validation_available:
            reason = RequirementCheckReason.GRAPH_UNAVAILABLE
        elif matches:
            reason = RequirementCheckReason.INVALID_EVIDENCE
        return RequirementAssessment.not_evaluated(
            identifier=identifier, kind=kind, reason=reason
        )

    found: RequirementAssessment = matches[0]
    if graph_accepted or found.status is not RequirementCheckStatus.SATISFIED:
        return found
    # Passing one check does not approve a structurally rejected topology.
    return found.model_copy(
        update={
            "status": RequirementCheckStatus.NOT_EVALUATED,
            "reason": RequirementCheckReason.GRAPH_UNACCEPTED,
        }
    )


def _coverage_status(
    assessments: list[RequirementAssessment], *, graph_accepted: bool
) -> RequirementCoverageStatus:
    """Keep unknown coverage separate from reported violations."""
    if not assessments:
        return RequirementCoverageStatus.NOT_APPLICABLE
    if any(item.status is RequirementCheckStatus.VIOLATED for item in assessments):
        return RequirementCoverageStatus.VIOLATED
    if not graph_accepted or any(
        item.status is RequirementCheckStatus.NOT_EVALUATED for item in assessments
    ):
        return RequirementCoverageStatus.INCOMPLETE
    return RequirementCoverageStatus.SATISFIED


def build_requirement_coverage_report(
    scenario: DesignScenario,
    *,
    graph_accepted: bool,
    validation: ValidationResult | None,
) -> RequirementCoverageReport:
    """Preserve one assessment per scenario occurrence, never assume success."""
    by_identifier: dict[str, list[RequirementAssessment]] = {}
    if validation is not None:
        for assessment in validation.requirement_assessments:
            by_identifier.setdefault(assessment.requirement_identifier, []).append(
                assessment
            )

    assessments: list[RequirementAssessment] = []
    for index, requirement in enumerate(scenario.requirements):
        identifier: str = requirement_identifier(index)
        assessments.append(
            _resolve_assessment(
                identifier,
                requirement.type_identifier,
                by_identifier.get(identifier, []),
                graph_accepted=graph_accepted,
                validation_available=validation is not None,
            )
        )

    return RequirementCoverageReport(
        scenario_identifier=scenario.identifier,
        graph_accepted=graph_accepted,
        status=_coverage_status(assessments, graph_accepted=graph_accepted),
        requirements=assessments,
    )
