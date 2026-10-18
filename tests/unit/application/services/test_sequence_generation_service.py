"""Characterization tests for sequence generation orchestration."""

from collections.abc import Sequence

import pytest

from application.exceptions.generation_exceptions import DesignProposalParsingError
from application.services.sequence_generation_service import SequenceGenerationService
from application.tasks import (
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
from domain.models.sequence import ComponentLifeline, InteractionScenario, UserLifeline
from domain.models.topology import ArchitectureGraph
from domain.specifications.interfaces import ValidationResult

pytestmark = pytest.mark.unit


class ValidCatalogValidator:
    def validate_catalog(self, catalog: ProjectRolesCatalog) -> ValidationResult:
        del catalog
        return ValidationResult()


class ValidScenarioValidator:
    def validate_scenario(
        self,
        scenario: InteractionScenario,
        catalog: ProjectRolesCatalog,
        graph: ArchitectureGraph,
        expected_requirement_id: str,
    ) -> ValidationResult:
        del scenario, catalog, graph, expected_requirement_id
        return ValidationResult()


class ScriptedSequenceDesigner:
    def __init__(
        self,
        role_script: Sequence[SequenceRoleProposal | DesignProposalParsingError],
        interaction_scripts: dict[
            str, list[SequenceInteractionProposal | DesignProposalParsingError]
        ],
    ) -> None:
        self.role_script = list(role_script)
        self.interaction_scripts = interaction_scripts
        self.role_tasks: list[SequenceRoleTask] = []
        self.interaction_tasks: list[SequenceInteractionTask] = []

    def propose_roles(self, task: SequenceRoleTask) -> SequenceRoleProposal:
        self.role_tasks.append(task)
        result = self.role_script.pop(0)
        if isinstance(result, DesignProposalParsingError):
            raise result
        return result

    def propose_interaction(
        self, task: SequenceInteractionTask
    ) -> SequenceInteractionProposal:
        self.interaction_tasks.append(task)
        result = self.interaction_scripts[task.requirement.identifier].pop(0)
        if isinstance(result, DesignProposalParsingError):
            raise result
        return result


def _scenario(requirement_ids: list[str]) -> DesignScenario:
    return DesignScenario(
        identifier="sequence_service_test",
        description="Sequence service test",
        functional_requirements=[
            FunctionalRequirement(
                identifier=req_id,
                name=f"Requirement {req_id}",
                text=f"Behavior described by {req_id}.",
            )
            for req_id in requirement_ids
        ],
    )


def _catalog() -> ProjectRolesCatalog:
    return ProjectRolesCatalog(
        roles=[
            BusinessRole(
                role_id="buyer",
                name="Buyer",
                description="User who initiates the interaction.",
            )
        ]
    )


def _interaction(requirement_id: str) -> InteractionScenario:
    return InteractionScenario(
        scenario_id=f"{requirement_id}_scenario",
        requirement_identifier=requirement_id,
        description=f"Interaction for {requirement_id}",
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
                description="Handles the request.",
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


def _role_proposal() -> SequenceRoleProposal:
    catalog = _catalog()
    return SequenceRoleProposal(
        payload=catalog,
        raw_content=catalog.model_dump_json(),
        usage=TokenUsage(prompt_tokens=10, completion_tokens=5),
    )


def _interaction_proposal(requirement_id: str) -> SequenceInteractionProposal:
    interaction = _interaction(requirement_id)
    return SequenceInteractionProposal(
        payload=interaction,
        raw_content=interaction.model_dump_json(),
        usage=TokenUsage(prompt_tokens=10, completion_tokens=5),
    )


def _parse_error() -> DesignProposalParsingError:
    return DesignProposalParsingError(
        raw_content="{ invalid json",
        failure_details=[
            ProposalFailureDetail(
                location="payload",
                message="Invalid JSON response",
                error_type="json_decode",
            )
        ],
        usage=TokenUsage(prompt_tokens=3, completion_tokens=2),
    )


def _service(
    designer: ScriptedSequenceDesigner, *, max_attempts: int = 2
) -> SequenceGenerationService:
    return SequenceGenerationService(
        designer=designer,  # type: ignore[arg-type]
        catalog_validators=[ValidCatalogValidator()],
        scenario_validators=[ValidScenarioValidator()],
        max_attempts=max_attempts,
        max_parallel_workers=1,
    )


def test_generation_skips_when_no_functional_requirements() -> None:
    designer = ScriptedSequenceDesigner([], {})
    result = _service(designer).generate(
        _scenario([]), ArchitectureGraph(nodes=[], edges=[])
    )

    assert result.roles_catalog is None
    assert result.scenarios_results == {}
    assert result.roles_attempts == []
    assert designer.role_tasks == []
    assert designer.interaction_tasks == []


def test_generation_returns_catalog_and_scenarios_in_requirement_order() -> None:
    designer = ScriptedSequenceDesigner(
        [_role_proposal()],
        {
            "FR-1": [_interaction_proposal("FR-1")],
            "FR-2": [_interaction_proposal("FR-2")],
        },
    )

    result = _service(designer).generate(
        _scenario(["FR-1", "FR-2"]), ArchitectureGraph(nodes=[], edges=[])
    )

    assert result.is_successful
    assert result.roles_catalog == _catalog()
    assert list(result.scenarios_results) == ["FR-1", "FR-2"]
    assert result.total_usage.total_tokens == 45


def test_catalog_parse_failure_is_retried_with_repair_task() -> None:
    designer = ScriptedSequenceDesigner(
        [_parse_error(), _role_proposal()],
        {"FR-1": [_interaction_proposal("FR-1")]},
    )

    result = _service(designer).generate(
        _scenario(["FR-1"]), ArchitectureGraph(nodes=[], edges=[])
    )

    assert result.is_successful
    assert [task.mode for task in designer.role_tasks] == [
        DesignTaskMode.INITIAL,
        DesignTaskMode.REPAIR,
    ]
    assert designer.role_tasks[1].previous_payload == "{ invalid json"
    assert result.roles_attempts[0].parsed is False
    assert result.roles_attempts[1].parsed is True


def test_failed_requirement_does_not_discard_successful_scenarios() -> None:
    designer = ScriptedSequenceDesigner(
        [_role_proposal()],
        {
            "FR-1": [_interaction_proposal("FR-1")],
            "FR-2": [_parse_error(), _parse_error()],
        },
    )

    result = _service(designer).generate(
        _scenario(["FR-1", "FR-2"]), ArchitectureGraph(nodes=[], edges=[])
    )

    assert result.is_successful is False
    assert list(result.scenarios_results) == ["FR-1", "FR-2"]
    assert result.scenarios_results["FR-1"].interaction_scenario is not None
    assert result.scenarios_results["FR-2"].interaction_scenario is None
