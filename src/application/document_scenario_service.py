"""Application service coordinating evidence validation and scenario mapping."""

from pathlib import Path

from pydantic import ValidationError

from application.document_processing import deduplicate_issues, is_evidence_supported
from application.document_scenario_functions import (
    CandidateValidationOptions,
    build_functional_requirements,
    build_metric_requirements,
    build_workload,
    resolve_candidate,
    slug_identifier,
    validate_source_backed_notes,
)
from application.document_scenario_ports import (
    DocumentRequirementsProvider,
    DocumentScenarioMapper,
)
from domain.document_requirements import (
    DocumentRequirements,
    RequirementEvidence,
    RequirementIssue,
    RequirementIssueKind,
    RequirementKind,
)
from domain.models.scenarios import DesignScenario
from domain.scenario_extraction import (
    DocumentScenarioResult,
    EvidenceValue,
)


class DocumentScenarioService:
    """Build a canonical scenario only from candidates with verifiable citations."""

    def __init__(
        self,
        requirements_service: DocumentRequirementsProvider,
        mapper: DocumentScenarioMapper,
    ) -> None:
        self._requirements_service = requirements_service
        self._mapper = mapper

    def extract_file(self, path: Path) -> DocumentScenarioResult:
        """Read a source document and map its verified claims to a scenario."""
        requirements = self._requirements_service.extract_file(path)
        return self.map_requirements(requirements)

    def map_requirements(
        self,
        requirements: DocumentRequirements,
    ) -> DocumentScenarioResult:
        """Map a pre-extracted result; useful for deterministic unit tests."""
        issues = list(requirements.issues)
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
                            "No source-grounded requirements remain after "
                            "evidence validation."
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
        issues.extend(
            validate_source_backed_notes(
                extraction.ambiguity_notes,
                verified_excerpts,
                RequirementIssueKind.AMBIGUOUS,
            )
        )
        issues.extend(
            validate_source_backed_notes(
                extraction.conflict_notes,
                verified_excerpts,
                RequirementIssueKind.CONFLICTING,
            )
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

        description_candidate = extraction.description
        if description_candidate.value is None:
            description_candidate = next(
                (
                    EvidenceValue[str](
                        value=requirement.statement,
                        source_excerpt=evidence.source_excerpt,
                    )
                    for requirement in requirements.requirements
                    if requirement.kind is RequirementKind.FUNCTIONAL
                    for evidence in requirement.source_evidence
                    if is_evidence_supported(
                        RequirementEvidence(source_excerpt=requirement.statement),
                        evidence.source_excerpt,
                    )
                ),
                description_candidate,
            )

        description_result = resolve_candidate(
            description_candidate,
            "description",
            verified_excerpts,
            options=CandidateValidationOptions(
                required=True,
                verbatim_text=True,
            ),
        )
        issues.extend(description_result.issues)
        field_evidence = dict(description_result.field_evidence)

        workload_result = build_workload(extraction.workload, verified_excerpts)
        issues.extend(workload_result.issues)
        field_evidence.update(dict(workload_result.field_evidence))

        metrics_result = build_metric_requirements(
            extraction.requirements,
            verified_excerpts,
        )
        issues.extend(metrics_result.issues)
        field_evidence.update(dict(metrics_result.field_evidence))

        functional_result = build_functional_requirements(
            extraction.functional_requirements,
            verified_excerpts,
        )
        issues.extend(functional_result.issues)
        field_evidence.update(dict(functional_result.field_evidence))

        scenario: DesignScenario | None = None
        if description_result.value is not None:
            try:
                scenario = DesignScenario(
                    identifier=slug_identifier(requirements.source_name),
                    description=description_result.value,
                    workload=workload_result.value,
                    requirements=metrics_result.value,
                    functional_requirements=functional_result.value,
                )
            except ValidationError as error:
                issues.append(
                    RequirementIssue(
                        kind=RequirementIssueKind.INVALID_VALUE,
                        field="scenario",
                        description=f"Scenario schema validation failed: {error}",
                    )
                )

        return DocumentScenarioResult(
            scenario=scenario,
            field_evidence=field_evidence,
            issues=deduplicate_issues(issues),
            is_relevant=True,
            source_name=requirements.source_name,
        )
