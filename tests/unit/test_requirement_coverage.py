"""Regression tests: unsupported NFRs must never masquerade as satisfied."""

from typing import Literal

import pytest
from pydantic import ValidationError

from application.requirement_coverage import build_requirement_coverage_report
from domain.models.base_constraints import BaseRequirement
from domain.models.nodes import ComputeNode
from domain.models.requirement_coverage import (
    RequirementAssessment,
    RequirementCheckReason,
    RequirementCheckStatus,
    RequirementCoverageReport,
    RequirementCoverageStatus,
)
from domain.models.requirements import (
    AvailabilityRequirement,
    BudgetRequirement,
    LatencyRequirement,
    QueueSizePercentileRequirement,
    Requirement,
    ResourceUtilizationRequirement,
)
from domain.models.scenarios import DesignScenario, WorkloadProfile
from domain.models.topology import ArchitectureGraph
from domain.specifications.budget_validator import BudgetRequirementValidator
from domain.specifications.interfaces import ValidationResult
from domain.specifications.requirement_dispatch import RequirementValidationDispatcher

pytestmark = pytest.mark.unit


def _graph() -> ArchitectureGraph:
    node = ComputeNode(
        identifier="orders",
        maximum_concurrency=5,
        maximum_queue_size=50,
        mean_processing_time_milliseconds=10.0,
        standard_deviation_processing_time=2.0,
        monthly_cost_usd=100.0,
    )
    return ArchitectureGraph(nodes=[node], edges=[])


def _scenario(*requirements: Requirement, workload: bool = True) -> DesignScenario:
    return DesignScenario(
        identifier="coverage",
        description="NFR evidence",
        requirements=list(requirements),
        workload=(
            WorkloadProfile(
                baseline_requests_per_second=10.0,
                peak_requests_per_second=20.0,
            )
            if workload
            else None
        ),
    )


def test_two_budgets_are_evaluated_independently() -> None:
    scenario: DesignScenario = _scenario(
        BudgetRequirement(threshold_value=200.0),
        BudgetRequirement(threshold_value=50.0),
    )
    validation: ValidationResult = RequirementValidationDispatcher(
        [BudgetRequirementValidator()]
    ).validate(_graph(), scenario)
    identifiers: list[str] = [
        item.requirement_identifier for item in validation.requirement_assessments
    ]
    assert identifiers == ["requirements[0]", "requirements[1]"]
    assert [item.status for item in validation.requirement_assessments] == [
        RequirementCheckStatus.SATISFIED,
        RequirementCheckStatus.VIOLATED,
    ]
    assert len(validation.errors) == 1


def test_known_unsupported_types_receive_explicit_reasons() -> None:
    scenario: DesignScenario = _scenario(
        AvailabilityRequirement(threshold_value=99.99),
        LatencyRequirement(threshold_value=150.0),
        QueueSizePercentileRequirement(threshold_value=10.0),
        ResourceUtilizationRequirement(minimum_value=10.0, maximum_value=85.0),
    )
    validation: ValidationResult = RequirementValidationDispatcher([]).validate(
        _graph(), scenario
    )
    assert not validation.errors
    assert [item.reason for item in validation.requirement_assessments] == [
        RequirementCheckReason.NO_VALIDATOR,
        RequirementCheckReason.NO_VALIDATOR,
        RequirementCheckReason.NO_VALIDATOR,
        RequirementCheckReason.NO_VALIDATOR,
    ]
    assert all(
        item.status is RequirementCheckStatus.NOT_EVALUATED
        for item in validation.requirement_assessments
    )


def test_missing_workload_is_not_silent_for_dependent_requirements() -> None:
    scenario: DesignScenario = _scenario(
        LatencyRequirement(threshold_value=150.0),
        QueueSizePercentileRequirement(threshold_value=10.0),
        ResourceUtilizationRequirement(minimum_value=0.0, maximum_value=80.0),
        workload=False,
    )
    validation: ValidationResult = RequirementValidationDispatcher([]).validate(
        _graph(), scenario
    )
    assert [item.reason for item in validation.requirement_assessments] == [
        RequirementCheckReason.MISSING_WORKLOAD
    ] * 3


class _UnregisteredRequirement(BaseRequirement):
    type_identifier: Literal["experimental"] = "experimental"

    def is_met_requirement(self, actual_value: float) -> bool:
        """Return failure for this intentionally unsupported requirement."""
        del actual_value
        return False


def test_programmatic_unknown_requirement_is_observable() -> None:
    scenario = DesignScenario.model_construct(
        identifier="unknown",
        description="Injected type outside discriminated union",
        requirements=[_UnregisteredRequirement()],
    )
    validation: ValidationResult = RequirementValidationDispatcher([]).validate(
        _graph(), scenario
    )
    assert len(validation.requirement_assessments) == 1
    assert (
        validation.requirement_assessments[0].reason
        is RequirementCheckReason.NO_VALIDATOR
    )
    assert validation.requirement_assessments[0].type_identifier == "experimental"


def test_report_is_incomplete_even_when_graph_generation_succeeds() -> None:
    scenario: DesignScenario = _scenario(
        BudgetRequirement(threshold_value=200.0),
        AvailabilityRequirement(threshold_value=99.99),
    )
    validation: ValidationResult = RequirementValidationDispatcher(
        [BudgetRequirementValidator()]
    ).validate(_graph(), scenario)
    report: RequirementCoverageReport = build_requirement_coverage_report(
        scenario, graph_accepted=True, validation=validation
    )
    assert report.graph_accepted
    assert report.status is RequirementCoverageStatus.INCOMPLETE
    assert [item.status for item in report.requirements] == [
        RequirementCheckStatus.SATISFIED,
        RequirementCheckStatus.NOT_EVALUATED,
    ]
    assert (
        RequirementCoverageReport.model_validate_json(report.model_dump_json())
        == report
    )


def test_unaccepted_graph_cannot_claim_a_passing_budget() -> None:
    scenario: DesignScenario = _scenario(BudgetRequirement(threshold_value=200.0))
    validation: ValidationResult = RequirementValidationDispatcher(
        [BudgetRequirementValidator()]
    ).validate(_graph(), scenario)
    report: RequirementCoverageReport = build_requirement_coverage_report(
        scenario, graph_accepted=False, validation=validation
    )
    assert report.status is RequirementCoverageStatus.INCOMPLETE
    assert report.requirements[0].reason is RequirementCheckReason.GRAPH_UNACCEPTED


def test_missing_graph_marks_all_requirements_not_evaluated() -> None:
    scenario: DesignScenario = _scenario(BudgetRequirement(threshold_value=200.0))
    report: RequirementCoverageReport = build_requirement_coverage_report(
        scenario, graph_accepted=False, validation=None
    )
    assert report.status is RequirementCoverageStatus.INCOMPLETE
    assert report.requirements[0].reason is RequirementCheckReason.GRAPH_UNAVAILABLE


def test_duplicate_assessment_cannot_overwrite_another_result() -> None:
    scenario: DesignScenario = _scenario(BudgetRequirement(threshold_value=200.0))
    validation: ValidationResult = RequirementValidationDispatcher(
        [BudgetRequirementValidator()]
    ).validate(_graph(), scenario)
    assessment: RequirementAssessment = validation.requirement_assessments[0]
    validation.requirement_assessments.append(assessment.model_copy())
    report: RequirementCoverageReport = build_requirement_coverage_report(
        scenario, graph_accepted=True, validation=validation
    )
    assert report.status is RequirementCoverageStatus.INCOMPLETE
    assert report.requirements[0].reason is RequirementCheckReason.INVALID_EVIDENCE


def test_type_mismatched_evidence_is_not_accepted() -> None:
    """Reject an assessment tied to the wrong requirement kind."""
    scenario: DesignScenario = _scenario(BudgetRequirement(threshold_value=200.0))
    validation: ValidationResult = RequirementValidationDispatcher(
        [BudgetRequirementValidator()]
    ).validate(_graph(), scenario)
    validation.requirement_assessments[0].type_identifier = "latency"

    report: RequirementCoverageReport = build_requirement_coverage_report(
        scenario, graph_accepted=True, validation=validation
    )
    assert report.status is RequirementCoverageStatus.INCOMPLETE
    assert report.requirements[0].reason is RequirementCheckReason.INVALID_EVIDENCE


def test_workload_requirement_flag_is_not_part_of_scenario_payload() -> None:
    """Keep prerequisite metadata internal rather than expanding YAML schema."""
    dependent_requirements: tuple[
        LatencyRequirement,
        QueueSizePercentileRequirement,
        ResourceUtilizationRequirement,
    ] = (
        LatencyRequirement(threshold_value=150.0),
        QueueSizePercentileRequirement(threshold_value=10.0),
        ResourceUtilizationRequirement(minimum_value=0.0, maximum_value=80.0),
    )
    for requirement in dependent_requirements:
        assert requirement.requires_workload
        assert "requires_workload" not in requirement.model_dump()

    assert not BudgetRequirement(threshold_value=100.0).requires_workload
    assert not AvailabilityRequirement(threshold_value=99.9).requires_workload


def test_all_checked_requirements_produce_satisfied_coverage() -> None:
    """The aggregate is satisfied only if every NFR is checked and passed."""
    scenario: DesignScenario = _scenario(BudgetRequirement(threshold_value=200.0))
    validation: ValidationResult = RequirementValidationDispatcher(
        [BudgetRequirementValidator()]
    ).validate(_graph(), scenario)

    report: RequirementCoverageReport = build_requirement_coverage_report(
        scenario, graph_accepted=True, validation=validation
    )

    assert report.status is RequirementCoverageStatus.SATISFIED
    assert report.requirements[0].status is RequirementCheckStatus.SATISFIED


def test_one_violation_takes_precedence_over_incomplete_coverage() -> None:
    """A rejected budget is observable even if availability was not checked."""
    scenario: DesignScenario = _scenario(
        BudgetRequirement(threshold_value=50.0),
        AvailabilityRequirement(threshold_value=99.99),
    )
    validation: ValidationResult = RequirementValidationDispatcher(
        [BudgetRequirementValidator()]
    ).validate(_graph(), scenario)

    report: RequirementCoverageReport = build_requirement_coverage_report(
        scenario, graph_accepted=True, validation=validation
    )

    assert report.status is RequirementCoverageStatus.VIOLATED
    assert [item.status for item in report.requirements] == [
        RequirementCheckStatus.VIOLATED,
        RequirementCheckStatus.NOT_EVALUATED,
    ]


def test_zero_requirements_have_not_applicable_coverage() -> None:
    """There is nothing to assess, which is neither success nor failure."""
    scenario: DesignScenario = _scenario()
    report: RequirementCoverageReport = build_requirement_coverage_report(
        scenario, graph_accepted=True, validation=ValidationResult()
    )

    assert report.status is RequirementCoverageStatus.NOT_APPLICABLE
    assert not report.requirements


def test_individual_and_aggregate_status_enums_reject_cross_level_values() -> None:
    """Prevent invalid per-requirement and summary states in the JSON contract."""
    with pytest.raises(ValidationError, match="status"):
        RequirementAssessment.model_validate(
            {
                "requirement_identifier": "requirements[0]",
                "type_identifier": "budget",
                "status": "incomplete",
            }
        )

    with pytest.raises(ValidationError, match="status"):
        RequirementCoverageReport.model_validate(
            {
                "scenario_identifier": "coverage",
                "graph_accepted": True,
                "status": "not_evaluated",
                "requirements": [],
            }
        )
