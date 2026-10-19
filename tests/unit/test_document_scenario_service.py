from pathlib import Path

import pytest

from application.document_scenario_service import DocumentScenarioService
from domain.document_requirements import (
    DocumentRequirements,
    Requirement,
    RequirementEvidence,
    RequirementIssueKind,
    RequirementKind,
    SourceBackedNote,
)
from domain.scenario_extraction import (
    DocumentScenarioExtraction,
    EvidenceValue,
    ExtractedFunctionalRequirement,
    ExtractedMetricRequirement,
    ExtractedWorkload,
)

BASELINE = "During normal operation, checkout should support 120 requests per second."
PEAK = "During a seasonal sale, traffic may reach 400 requests per second."
LATENCY = "The checkout API should respond within 300 ms at the 95th percentile under normal load."
AVAILABILITY = "The service should be available at least 99.9% of each calendar month."
FUNCTIONAL = "A customer can add one or more products to a shopping cart."


def make_source_requirements() -> DocumentRequirements:
    excerpts = [BASELINE, PEAK, LATENCY, AVAILABILITY, FUNCTIONAL]
    return DocumentRequirements(
        requirements=[
            Requirement(
                statement=excerpt,
                kind=(
                    RequirementKind.NON_FUNCTIONAL
                    if excerpt in {BASELINE, PEAK, LATENCY, AVAILABILITY}
                    else RequirementKind.FUNCTIONAL
                ),
                source_evidence=[RequirementEvidence(source_excerpt=excerpt)],
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
            read_ratio=EvidenceValue(value=None, source_excerpt=None),
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
                type_identifier=EvidenceValue(value="availability", source_excerpt=AVAILABILITY),
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
    def __init__(self, result: DocumentRequirements) -> None:
        self.result = result

    def extract_file(self, path: Path) -> DocumentRequirements:
        return self.result


class FakeMapper:
    def __init__(self, result: DocumentScenarioExtraction) -> None:
        self.result = result
        self.calls = 0

    def map(self, requirements: DocumentRequirements) -> DocumentScenarioExtraction:
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
    assert result.scenario.description == "Online store checkout requirements."
    assert result.scenario.workload is not None
    assert result.scenario.workload.baseline_requests_per_second == 120.0
    assert result.scenario.workload.peak_requests_per_second == 400.0
    assert len(result.scenario.requirements) == 2
    assert result.scenario.functional_requirements[0].identifier == "FR-001"
    assert result.field_evidence["workload.baseline_requests_per_second"] == BASELINE
    assert result.field_evidence["requirements[0].type_identifier"] == LATENCY
    assert any(
        issue.kind is RequirementIssueKind.MISSING
        and issue.field == "workload.read_ratio"
        for issue in result.issues
    )


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
        issue.kind is RequirementIssueKind.UNSUPPORTED_EVIDENCE
        and issue.field == "workload.baseline_requests_per_second"
        for issue in result.issues
    )


@pytest.mark.unit
def test_discards_scenario_diagnostics_with_unverified_citations() -> None:
    source = make_source_requirements()
    mapping = make_mapping()
    mapping.ambiguity_notes = [
        SourceBackedNote(
            description="The source requires biometric login.",
            source_evidence=[
                RequirementEvidence(source_excerpt="The source requires biometric login.")
            ],
        )
    ]

    result = DocumentScenarioService(
        FakeRequirementsService(source), FakeMapper(mapping)
    ).map_requirements(source)

    assert any(
        issue.kind is RequirementIssueKind.UNSUPPORTED_EVIDENCE
        and "biometric login" in issue.description
        for issue in result.issues
    )
    assert not any(
        issue.kind is RequirementIssueKind.AMBIGUOUS
        and "biometric login" in issue.description
        for issue in result.issues
    )


@pytest.mark.unit
def test_does_not_call_mapper_for_irrelevant_or_ungrounded_document() -> None:
    source = DocumentRequirements(
        requirements=[], is_relevant=False, source_name="notes.md"
    )
    mapper = FakeMapper(make_mapping())
    result = DocumentScenarioService(FakeRequirementsService(source), mapper).map_requirements(
        source
    )

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
        issue.kind is RequirementIssueKind.UNSUPPORTED_EVIDENCE
        and issue.field == "functional_requirements[0].text"
        for issue in result.issues
    )
