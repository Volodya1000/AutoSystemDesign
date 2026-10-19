"""Unit tests for sequence generation repair loops and partial results."""

from collections.abc import Sequence

import pytest

from application.exceptions.generation_exceptions import DesignProposalParsingError
from application.results import SequenceGenerationResult
from application.services.sequence_generation_service import SequenceGenerationService
from application.tasks import (
    JSON_DECODE_ERROR_TYPE,
    DesignTaskMode,
    ProposalFailureDetail,
    SequenceInteractionProposal,
    SequenceInteractionTask,
    SequenceRoleProposal,
    SequenceRoleTask,
)
from application.usage import TokenUsage
from domain.models.ast_steps import MessageStep
from domain.models.functional import FunctionalRequirement
from domain.models.roles import BusinessRole, ProjectRolesCatalog
from domain.models.scenarios import DesignScenario
from domain.models.sequence import (
    ComponentLifeline,
    InteractionScenario,
    UserLifeline,
)
from domain.models.topology import ArchitectureGraph
from domain.specifications.interfaces import ValidationResult
from domain.specifications.sequence_validator import (
    SequenceCatalogValidator,
    SequenceIntegrityError,
    SequenceScenarioValidator,
)

pytestmark = pytest.mark.unit


def _requirement(identifier: str = "FR-1") -> FunctionalRequirement:
    return FunctionalRequirement(
        identifier=identifier,
        name=f"Requirement {identifier}",
        text=f"A user completes {identifier}.",
    )


def _scenario(
    requirements: list[FunctionalRequirement] | None = None,
) -> DesignScenario:
    return DesignScenario(
        identifier="sequence_service_test",
        description="Sequence generation test",
        functional_requirements=(
            [_requirement()] if requirements is None else requirements
        ),
    )


def _catalog() -> ProjectRolesCatalog:
    return ProjectRolesCatalog(
        roles=[
            BusinessRole(
                role_id="buyer",
                name="Buyer",
                description="A user who initiates the interaction.",
            )
        ]
    )


def _interaction(requirement_id: str = "FR-1") -> InteractionScenario:
    return InteractionScenario(
        scenario_id=f"{requirement_id}_scenario",
        requirement_identifier=requirement_id,
        description=f"Handle {requirement_id}",
        lifelines=[
            UserLifeline(
                kind="user",
                lifeline_id="buyer_1",
                business_role_id="buyer",
                scenario_role="initiator",
                description="The buyer initiating the request.",
            ),
            ComponentLifeline(
                kind="component",
                lifeline_id="api_1",
                architecture_node_id="api",
                display_name="API",
                description="The API entry point.",
            ),
        ],
        steps=[
            MessageStep(
                kind="message",
                from_lifeline="buyer_1",
                to_lifeline="api_1",
                action_name="POST /resources",
                message_kind="user_action",
                delivery_mode="sync",
            )
        ],
    )


def _role_proposal(
    catalog: ProjectRolesCatalog | None = None,
    *,
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> SequenceRoleProposal:
    return SequenceRoleProposal(
        payload=_catalog() if catalog is None else catalog,
        raw_content="roles payload",
        usage=TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        ),
        latency_seconds=0.2,
    )


def _interaction_proposal(
    requirement_id: str = "FR-1",
    *,
    prompt_tokens: int = 20,
    completion_tokens: int = 10,
) -> SequenceInteractionProposal:
    return SequenceInteractionProposal(
        payload=_interaction(requirement_id),
        raw_content=f"interaction payload {requirement_id}",
        usage=TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        ),
        latency_seconds=0.4,
    )


def _parsing_failure(prompt_tokens: int = 3) -> DesignProposalParsingError:
    return DesignProposalParsingError(
        raw_content="not valid JSON",
        failure_details=[
            ProposalFailureDetail(
                location="$",
                message="invalid JSON",
                error_type=JSON_DECODE_ERROR_TYPE,
            )
        ],
        usage=TokenUsage(prompt_tokens=prompt_tokens, completion_tokens=1),
    )


class FakeSequenceDesigner:
    """Scripted designer that records tasks and raises scripted parse failures."""

    def __init__(
        self,
        role_script: Sequence[SequenceRoleProposal | DesignProposalParsingError],
        interaction_scripts: dict[
            str, Sequence[SequenceInteractionProposal | DesignProposalParsingError]
        ]
        | None = None,
    ) -> None:
        self._role_script: list[SequenceRoleProposal | DesignProposalParsingError] = (
            list(role_script)
        )
        self._interaction_scripts: dict[
            str, list[SequenceInteractionProposal | DesignProposalParsingError]
        ] = {
            requirement_id: list(script)
            for requirement_id, script in (interaction_scripts or {}).items()
        }
        self.role_tasks: list[SequenceRoleTask] = []
        self.interaction_tasks: list[SequenceInteractionTask] = []

    def propose_roles(self, task: SequenceRoleTask) -> SequenceRoleProposal:
        self.role_tasks.append(task)
        if not self._role_script:
            raise AssertionError("Unexpected extra propose_roles call")
        item = self._role_script.pop(0)
        if isinstance(item, DesignProposalParsingError):
            raise item
        return item

    def propose_interaction(
        self, task: SequenceInteractionTask
    ) -> SequenceInteractionProposal:
        self.interaction_tasks.append(task)
        script = self._interaction_scripts[task.requirement.identifier]
        if not script:
            raise AssertionError("Unexpected extra propose_interaction call")
        item = script.pop(0)
        if isinstance(item, DesignProposalParsingError):
            raise item
        return item


class ScriptedCatalogValidator:
    def __init__(self, results: Sequence[ValidationResult] = ()) -> None:
        self._results: list[ValidationResult] = list(results)

    def validate_catalog(self, catalog: ProjectRolesCatalog) -> ValidationResult:
        del catalog
        return self._results.pop(0) if self._results else ValidationResult()


class ScriptedScenarioValidator:
    def __init__(
        self,
        results_by_requirement: dict[str, Sequence[ValidationResult]] | None = None,
    ) -> None:
        self._results: dict[str, list[ValidationResult]] = {
            identifier: list(results)
            for identifier, results in (results_by_requirement or {}).items()
        }

    def validate_scenario(
        self,
        scenario: InteractionScenario,
        catalog: ProjectRolesCatalog,
        graph: ArchitectureGraph,
        expected_requirement_id: str,
    ) -> ValidationResult:
        del scenario, catalog, graph
        results = self._results.get(expected_requirement_id, [])
        return results.pop(0) if results else ValidationResult()


def _service(
    designer: FakeSequenceDesigner,
    *,
    catalog_validator: SequenceCatalogValidator | None = None,
    scenario_validator: SequenceScenarioValidator | None = None,
    max_attempts: int = 3,
    max_parallel_workers: int = 1,
) -> SequenceGenerationService:
    return SequenceGenerationService(
        designer=designer,
        catalog_validators=[
            ScriptedCatalogValidator()
            if catalog_validator is None
            else catalog_validator
        ],
        scenario_validators=[
            ScriptedScenarioValidator()
            if scenario_validator is None
            else scenario_validator
        ],
        max_attempts=max_attempts,
        max_parallel_workers=max_parallel_workers,
    )


def test_retries_parsing_failures_and_preserves_repair_context() -> None:
    role_failure = _parsing_failure(prompt_tokens=3)
    interaction_failure = _parsing_failure(prompt_tokens=7)
    designer = FakeSequenceDesigner(
        [role_failure, _role_proposal(prompt_tokens=10, completion_tokens=5)],
        {"FR-1": [interaction_failure, _interaction_proposal()]},
    )

    result: SequenceGenerationResult = _service(designer).generate(
        _scenario(), ArchitectureGraph(nodes=[], edges=[])
    )

    assert result.roles_catalog is not None
    assert result.is_successful
    assert len(result.roles_attempts) == 2
    assert result.roles_attempts[0].parsed is False
    assert result.roles_attempts[0].usage == role_failure.usage
    assert designer.role_tasks[0].mode is DesignTaskMode.INITIAL
    role_repair = designer.role_tasks[1]
    assert role_repair.mode is DesignTaskMode.REPAIR
    assert role_repair.previous_payload == role_failure.raw_content
    assert role_repair.parsing_failures == role_failure.failure_details

    interaction_result = result.scenarios_results["FR-1"]
    assert interaction_result.is_successful
    assert len(interaction_result.attempts) == 2
    interaction_repair = designer.interaction_tasks[1]
    assert interaction_repair.mode is DesignTaskMode.REPAIR
    assert interaction_repair.previous_payload == interaction_failure.raw_content
    assert interaction_repair.parsing_failures == interaction_failure.failure_details
    assert result.total_usage == TokenUsage(prompt_tokens=40, completion_tokens=17)


def test_catalog_validation_feedback_is_sent_to_repair_attempt() -> None:
    invalid_result = ValidationResult(
        errors=[SequenceIntegrityError("role catalog contains a conflict")]
    )
    designer = FakeSequenceDesigner(
        [_role_proposal(), _role_proposal(prompt_tokens=12, completion_tokens=6)],
        {"FR-1": [_interaction_proposal()]},
    )
    validator = ScriptedCatalogValidator([invalid_result, ValidationResult()])

    result = _service(designer, catalog_validator=validator).generate(
        _scenario(), ArchitectureGraph(nodes=[], edges=[])
    )

    assert result.roles_catalog is not None
    assert len(result.roles_attempts) == 2
    repair = designer.role_tasks[1]
    first_payload = result.roles_attempts[0].payload
    assert first_payload is not None
    assert repair.mode is DesignTaskMode.REPAIR
    assert repair.previous_payload == first_payload.model_dump_json()
    assert repair.validation_feedback[0].error_code == "SEQUENCE_INTEGRITY_ERROR"


def test_interaction_validation_feedback_is_sent_to_repair_attempt() -> None:
    invalid_result = ValidationResult(
        errors=[SequenceIntegrityError("scenario references an unknown role")]
    )
    designer = FakeSequenceDesigner(
        [_role_proposal()],
        {"FR-1": [_interaction_proposal(), _interaction_proposal(prompt_tokens=25)]},
    )
    validator = ScriptedScenarioValidator(
        {"FR-1": [invalid_result, ValidationResult()]}
    )

    result = _service(designer, scenario_validator=validator).generate(
        _scenario(), ArchitectureGraph(nodes=[], edges=[])
    )

    assert result.is_successful
    assert len(result.scenarios_results["FR-1"].attempts) == 2
    repair = designer.interaction_tasks[1]
    first_payload = result.scenarios_results["FR-1"].attempts[0].payload
    assert first_payload is not None
    assert repair.mode is DesignTaskMode.REPAIR
    assert repair.previous_payload == first_payload.model_dump_json()
    assert repair.validation_feedback[0].error_code == "SEQUENCE_INTEGRITY_ERROR"


def test_rejects_invalid_parallelism_and_missing_validators() -> None:
    designer = FakeSequenceDesigner([_role_proposal()])

    with pytest.raises(ValueError, match="at least 1"):
        SequenceGenerationService(
            designer=designer,
            catalog_validators=[ScriptedCatalogValidator()],
            scenario_validators=[ScriptedScenarioValidator()],
            max_attempts=1,
            max_parallel_workers=0,
        )
    with pytest.raises(ValueError, match="At least one catalog validator"):
        SequenceGenerationService(
            designer=designer,
            catalog_validators=[],
            scenario_validators=[ScriptedScenarioValidator()],
            max_attempts=1,
        )
    with pytest.raises(ValueError, match="At least one scenario validator"):
        SequenceGenerationService(
            designer=designer,
            catalog_validators=[ScriptedCatalogValidator()],
            scenario_validators=[],
            max_attempts=1,
        )


def test_aborts_interactions_when_roles_catalog_never_parses() -> None:
    designer = FakeSequenceDesigner(
        [_parsing_failure(prompt_tokens=3), _parsing_failure(prompt_tokens=5)]
    )

    result = _service(designer, max_attempts=2).generate(
        _scenario(), ArchitectureGraph(nodes=[], edges=[])
    )

    assert result.roles_catalog is None
    assert len(result.roles_attempts) == 2
    assert result.scenarios_results == {}
    assert not designer.interaction_tasks
    assert result.total_usage == TokenUsage(prompt_tokens=8, completion_tokens=2)
