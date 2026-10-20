from pathlib import Path

import pytest

from application.document_scenario_service import DocumentScenarioService
from domain import document_requirements as req_doc
from domain.scenario_extraction import (
    DocumentScenarioExtraction,
    EvidenceValue,
    ExtractedFunctionalRequirement,
    ExtractedMetricRequirement,
    ExtractedWorkload,
)
from tests.test_support import has_issue

BASELINE = "During normal operation, checkout should support 120 requests per second."
PEAK = "During a seasonal sale, traffic may reach 400 requests per second."
LATENCY = (
    "The checkout API should respond within 300 ms at the 95th percentile under "
    "normal load."
)
AVAILABILITY = "The service should be available at least 99.9% of each calendar month."
FUNCTIONAL = "A customer can add one or more products to a shopping cart."
READ_RATIO = "Read requests account for 0.7 of total traffic."


def make_source_requirements() -> req_doc.DocumentRequirements:
    excerpts = [BASELINE, PEAK, READ_RATIO, LATENCY, AVAILABILITY, FUNCTIONAL]
    return req_doc.DocumentRequirements(
        requirements=[
            req_doc.Requirement(
                statement=excerpt,
                kind=(
                    req_doc.RequirementKind.NON_FUNCTIONAL
                    if excerpt in {BASELINE, PEAK, READ_RATIO, LATENCY, AVAILABILITY}
                    else req_doc.RequirementKind.FUNCTIONAL
                ),
                source_evidence=[req_doc.RequirementEvidence(source_excerpt=excerpt)],
            )
            for excerpt in excerpts
        ],
        is_relevant=True,
        source_name="spec.md",
    )


def make_mapping() -> DocumentScenarioExtraction:
    return DocumentScenarioExtraction(
        description=EvidenceValue(value=FUNCTIONAL, source_excerpt=FUNCTIONAL),
        workload=ExtractedWorkload(
            baseline_requests_per_second=EvidenceValue(
                value=120.0, source_excerpt=BASELINE
            ),
            peak_requests_per_second=EvidenceValue(value=400.0, source_excerpt=PEAK),
            read_ratio=EvidenceValue(value=0.7, source_excerpt=READ_RATIO),
        ),
        requirements=[
            ExtractedMetricRequirement(
                type_identifier=EvidenceValue(value="latency", source_excerpt=LATENCY),
                threshold_value=EvidenceValue(value=300.0, source_excerpt=LATENCY),
                percentile=EvidenceValue(value=95.0, source_excerpt=LATENCY),
                minimum_value=EvidenceValue(value=None, source_excerpt=None),
                maximum_value=EvidenceValue(value=None, source_excerpt=None),
            ),
            ExtractedMetricRequirement(
                type_identifier=EvidenceValue(
                    value="availability", source_excerpt=AVAILABILITY
                ),
                threshold_value=EvidenceValue(value=99.9, source_excerpt=AVAILABILITY),
                percentile=EvidenceValue(value=None, source_excerpt=None),
                minimum_value=EvidenceValue(value=None, source_excerpt=None),
                maximum_value=EvidenceValue(value=None, source_excerpt=None),
            ),
        ],
        functional_requirements=[
            ExtractedFunctionalRequirement(
                text=EvidenceValue(value=FUNCTIONAL, source_excerpt=FUNCTIONAL)
            )
        ],
        is_relevant=True,
        ambiguity_notes=[],
        conflict_notes=[],
    )


class FakeRequirementsService:
    def __init__(self, result: req_doc.DocumentRequirements) -> None:
        self.result = result

    def extract_file(self, _path: Path) -> req_doc.DocumentRequirements:
        return self.result


class FakeMapper:
    def __init__(self, result: DocumentScenarioExtraction) -> None:
        self.result = result
        self.calls = 0

    def map(
        self, _requirements: req_doc.DocumentRequirements
    ) -> DocumentScenarioExtraction:
        self.calls += 1
        return self.result


@pytest.mark.unit
def test_maps_verified_fields_into_pipeline_compatible_scenario() -> None:
    service = DocumentScenarioService(
        FakeRequirementsService(make_source_requirements()), FakeMapper(make_mapping())
    )

    result = service.map_requirements(make_source_requirements())

    assert result.scenario is not None
    assert result.scenario.identifier == "spec"
    assert result.scenario.description == FUNCTIONAL
    assert result.scenario.workload is not None
    assert result.scenario.workload.baseline_requests_per_second == EXPECTED_ASSERT_RESULT_SCENARIO_WORKLOAD_BASELINE
    assert result.scenario.workload.peak_requests_per_second == EXPECTED_ASSERT_RESULT_SCENARIO_WORKLOAD_PEAK_REQ
    assert result.scenario.workload.read_ratio == EXPECTED_ASSERT_RESULT_SCENARIO_WORKLOAD_READ_RAT
    assert len(result.scenario.requirements) == EXPECTED_ASSERT_RESULT_SCENARIO_REQUIREMENTS_COUN
    assert result.scenario.functional_requirements[0].identifier == "FR-001"
    assert result.field_evidence["workload.baseline_requests_per_second"] == BASELINE
    assert result.field_evidence["requirements[0].type_identifier"] == LATENCY
    assert result.field_evidence["workload.read_ratio"] == READ_RATIO


@pytest.mark.unit
def test_does_not_accept_numeric_value_not_present_in_verified_evidence() -> None:
    source = make_source_requirements()
    mapping = make_mapping()
    mapping.workload.baseline_requests_per_second = EvidenceValue(
        value=200.0, source_excerpt=BASELINE
    )
    result = DocumentScenarioService(
        FakeRequirementsService(source), FakeMapper(mapping)
    ).map_requirements(source)

    assert result.scenario is not None
    assert result.scenario.workload is None
    assert any(
        issue.kind is req_doc.RequirementIssueKind.UNSUPPORTED_EVIDENCE
        and issue.field == "workload.baseline_requests_per_second"
        for issue in result.issues
    )


@pytest.mark.unit
def test_discards_scenario_diagnostics_with_unverified_citations() -> None:
    source = make_source_requirements()
    mapping = make_mapping()
    mapping.ambiguity_notes = [
        req_doc.SourceBackedNote(
            description="The source requires biometric login.",
            source_evidence=[req_doc.RequirementEvidence(source_excerpt=FUNCTIONAL)],
        )
    ]

    result = DocumentScenarioService(
        FakeRequirementsService(source), FakeMapper(mapping)
    ).map_requirements(source)

    assert has_issue(
        result.issues,
        req_doc.RequirementIssueKind.UNSUPPORTED_EVIDENCE,
        description_contains="biometric login",
    )
    assert not has_issue(
        result.issues,
        req_doc.RequirementIssueKind.AMBIGUOUS,
        description_contains="biometric login",
    )


@pytest.mark.unit
def test_does_not_call_mapper_for_irrelevant_or_ungrounded_document() -> None:
    source = req_doc.DocumentRequirements(
        requirements=[], is_relevant=False, source_name="notes.md"
    )
    mapper = FakeMapper(make_mapping())
    result = DocumentScenarioService(
        FakeRequirementsService(source), mapper
    ).map_requirements(source)

    assert result.scenario is None
    assert not result.is_relevant
    assert mapper.calls == 0


@pytest.mark.unit
def test_rejects_functional_text_not_present_in_its_citation() -> None:
    source = make_source_requirements()
    mapping = make_mapping()
    mapping.functional_requirements = [
        ExtractedFunctionalRequirement(
            text=EvidenceValue(
                value="The system guarantees biometric authentication.",
                source_excerpt=FUNCTIONAL,
            )
        )
    ]

    result = DocumentScenarioService(
        FakeRequirementsService(source), FakeMapper(mapping)
    ).map_requirements(source)

    assert result.scenario is not None
    assert result.scenario.functional_requirements == []
    assert any(
        issue.kind is req_doc.RequirementIssueKind.UNSUPPORTED_EVIDENCE
        and issue.field == "functional_requirements[0].text"
        for issue in result.issues
    )


@pytest.mark.unit
def test_omits_incomplete_workload_instead_of_using_default_ratio() -> None:
    source = make_source_requirements()
    source.requirements = [
        requirement
        for requirement in source.requirements
        if requirement.statement != READ_RATIO
    ]
    mapping = make_mapping()
    mapping.workload.read_ratio = EvidenceValue(value=None, source_excerpt=None)

    result = DocumentScenarioService(
        FakeRequirementsService(source), FakeMapper(mapping)
    ).map_requirements(source)

    assert result.scenario is not None
    assert result.scenario.workload is None
    assert "workload.read_ratio" not in result.field_evidence
    assert any(
        issue.kind is req_doc.RequirementIssueKind.MISSING
        and issue.field == "workload.read_ratio"
        for issue in result.issues
    )


@pytest.mark.unit
def test_rejects_partial_citation_even_when_numeric_value_is_present() -> None:
    source = make_source_requirements()
    mapping = make_mapping()
    mapping.workload.baseline_requests_per_second = EvidenceValue(
        value=120.0, source_excerpt="120 requests per second"
    )

    result = DocumentScenarioService(
        FakeRequirementsService(source), FakeMapper(mapping)
    ).map_requirements(source)

    assert result.scenario is not None
    assert result.scenario.workload is None
    assert any(
        issue.kind is req_doc.RequirementIssueKind.UNSUPPORTED_EVIDENCE
        and issue.field == "workload.baseline_requests_per_second"
        for issue in result.issues
    )


@pytest.mark.unit
def test_uses_verified_functional_requirement_when_description_is_missing() -> None:
    source = make_source_requirements()
    mapping = make_mapping()
    mapping.description = EvidenceValue(value=None, source_excerpt=None)

    result = DocumentScenarioService(
        FakeRequirementsService(source), FakeMapper(mapping)
    ).map_requirements(source)

    assert result.scenario is not None
    assert result.scenario.description == FUNCTIONAL
    assert result.field_evidence["description"] == FUNCTIONAL
    assert not any(
        issue.kind is req_doc.RequirementIssueKind.MISSING
        and issue.field == "description"
        for issue in result.issues
    )


@pytest.mark.unit
def test_keeps_synthesized_conflict_when_all_source_excerpts_are_verified() -> None:
    source = make_source_requirements()
    first = "The confirmation email must be sent within 10 seconds."
    second = "Confirmation emails may be delayed 2 minutes during peak traffic."
    source.requirements.extend(
        [
            req_doc.Requirement(
                statement=excerpt,
                kind=req_doc.RequirementKind.NON_FUNCTIONAL,
                source_evidence=[req_doc.RequirementEvidence(source_excerpt=excerpt)],
            )
            for excerpt in (first, second)
        ]
    )
    mapping = make_mapping()
    mapping.conflict_notes = [
        req_doc.SourceBackedNote(
            description=(
                "The email delivery target conflicts with the permitted peak delay."
            ),
            source_evidence=[
                req_doc.RequirementEvidence(source_excerpt=first),
                req_doc.RequirementEvidence(source_excerpt=second),
            ],
        )
    ]

    result = DocumentScenarioService(
        FakeRequirementsService(source), FakeMapper(mapping)
    ).map_requirements(source)

    conflict_issues = [
        issue
        for issue in result.issues
        if issue.kind is req_doc.RequirementIssueKind.CONFLICTING
    ]
    assert len(conflict_issues) == 1
    assert conflict_issues[0].evidence == [first, second]

EXPECTED_ASSERT_RESULT_SCENARIO_REQUIREMENTS_COUN = 2
EXPECTED_ASSERT_RESULT_SCENARIO_WORKLOAD_READ_RAT = 0.7
EXPECTED_ASSERT_RESULT_SCENARIO_WORKLOAD_PEAK_REQ = 400.0
EXPECTED_ASSERT_RESULT_SCENARIO_WORKLOAD_BASELINE = 120.0
