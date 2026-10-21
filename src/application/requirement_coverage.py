"""Build a per-requirement coverage report from recorded validation evidence."""

from application.results import DesignGenerationResult, GenerationStatus
from domain.models.requirement_coverage import (
    RequirementAssessment,
    RequirementCheckReason,
    RequirementCheckStatus,
    RequirementCoverageReport,
    RequirementCoverageStatus,
    requirement_identifier,
)
from domain.models.scenarios import DesignScenario



def build_requirement_coverage_report(
    scenario: DesignScenario,
    generation: DesignGenerationResult,
) -> RequirementCoverageReport:
    """Never infer an assessment from a successful pipeline exit code."""
    accepted = generation.status is GenerationStatus.SUCCEEDED
    validation = generation.attempts[-1].validation
    by_identifier = (
        {
            item.requirement_identifier: item
            for item in validation.requirement_assessments
        }
        if validation is not None
        else {}
    )
    assessments: list[RequirementAssessment] = []

    for index, requirement in enumerate(scenario.requirements):
        identifier = requirement_identifier(index)
        kind = requirement.type_identifier
        found = by_identifier.get(identifier)
        if found is None or found.type_identifier != kind:
            assessments.append(
                RequirementAssessment.not_evaluated(
                    identifier=identifier,
                    kind=kind,
                    reason=(
                        RequirementCheckReason.GRAPH_UNAVAILABLE
                        if validation is None
                        else RequirementCheckReason.NO_VALIDATOR
                    ),
                )
            )
            continue

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
