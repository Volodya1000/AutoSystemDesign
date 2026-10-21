"""Build a per-requirement coverage report from recorded validation evidence."""

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


def build_requirement_coverage_report(
    scenario: DesignScenario,
    *,
    graph_accepted: bool,
    validation: ValidationResult | None,
) -> RequirementCoverageReport:
    """Only explicit validation evidence can establish compliance."""
    accepted = graph_accepted
    by_identifier: dict[str, list[RequirementAssessment]] = {}
    if validation is not None:
        for assessment in validation.requirement_assessments:
            by_identifier.setdefault(assessment.requirement_identifier, []).append(
                assessment
            )
    assessments: list[RequirementAssessment] = []

    for index, requirement in enumerate(scenario.requirements):
        identifier = requirement_identifier(index)
        kind = requirement.type_identifier
        matches = by_identifier.get(identifier, [])
        if len(matches) != 1 or matches[0].type_identifier != kind:
            reason = RequirementCheckReason.NO_VALIDATOR
            if validation is None:
                reason = RequirementCheckReason.GRAPH_UNAVAILABLE
            elif len(matches) > 1:
                reason = RequirementCheckReason.AMBIGUOUS_EVIDENCE
            elif matches:
                reason = RequirementCheckReason.EVIDENCE_TYPE_MISMATCH
            assessments.append(
                RequirementAssessment.not_evaluated(
                    identifier=identifier, kind=kind, reason=reason
                )
            )
            continue

        found = matches[0]
        if not accepted and found.status is RequirementCheckStatus.SATISFIED:
            # A passing check on a rejected candidate is not an accepted design.
            found = found.model_copy(
                update={
                    "status": RequirementCheckStatus.NOT_EVALUATED,
                    "reason": RequirementCheckReason.GRAPH_UNACCEPTED,
                }
            )
        assessments.append(found)

    if not assessments:
        status = RequirementCoverageStatus.NOT_APPLICABLE
    elif any(
        item.status is RequirementCheckStatus.VIOLATED for item in assessments
    ):
        status = RequirementCoverageStatus.VIOLATED
    elif not accepted or any(
        item.status is RequirementCheckStatus.NOT_EVALUATED for item in assessments
    ):
        status = RequirementCoverageStatus.INCOMPLETE
    else:
        status = RequirementCoverageStatus.SATISFIED

    return RequirementCoverageReport(
        scenario_identifier=scenario.identifier,
        graph_accepted=accepted,
        status=status,
        requirements=assessments,
    )
