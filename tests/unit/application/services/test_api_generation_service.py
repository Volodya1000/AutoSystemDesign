"""Unit tests for the API design generation and repair loop."""

from collections.abc import Sequence

import pytest

from application.exceptions.generation_exceptions import DesignProposalParsingError
from application.results import ApiGenerationResult, GenerationStatus
from application.services.api_generation_service import ApiGenerationService
from application.tasks import (
    ApiDesignProposal,
    ApiDesignTask,
    DesignTaskMode,
    ProposalFailureDetail,
)
from application.usage import TokenUsage
from domain.models.api import ApiDesign, ApiOperation, ApiResponse, HttpMethod
from domain.models.functional import FunctionalRequirement
from domain.models.nodes import ComputeNode
from domain.models.scenarios import DesignScenario
from domain.models.topology import ArchitectureGraph
from domain.specifications.api_validator import ApiDesignValidator

from tests.unit.constants import EXPECTED_RESULT_ATTEMPTS_COUNT

EXPECTED_TOTAL_TOKENS = 40

pytestmark = pytest.mark.unit


def _scenario() -> DesignScenario:
    return DesignScenario(
        identifier="api_generation_test",
        description="API generation test",
        functional_requirements=[
            FunctionalRequirement(
                identifier="FR-1",
                name="Create resource",
                text="A user creates a resource.",
            )
        ],
    )


def _graph() -> ArchitectureGraph:
    return ArchitectureGraph(
        nodes=[
            ComputeNode(
                identifier="api",
                maximum_concurrency=100,
                maximum_queue_size=100,
                mean_processing_time_milliseconds=10.0,
                standard_deviation_processing_time=2.0,
                monthly_cost_usd=100.0,
            )
        ],
        edges=[],
    )


def _api_design(*, handler_component_id: str = "api") -> ApiDesign:
    return ApiDesign(
        title="Test API",
        operations=[
            ApiOperation(
                operation_id="create_resource",
                method=HttpMethod.POST,
                path="/v1/resources",
                summary="Create a resource",
                entrypoint_component_id="api",
                handler_component_id=handler_component_id,
                requirement_ids=["FR-1"],
                responses=[ApiResponse(status_code="201", description="Created")],
            )
        ],
    )


def _proposal(api: ApiDesign) -> ApiDesignProposal:
    return ApiDesignProposal(
        payload=api,
        raw_content=api.model_dump_json(),
        usage=TokenUsage(prompt_tokens=10, completion_tokens=20),
    )


class ScriptedApiDesigner:
    """Returns scripted proposals and records the tasks received."""

    def __init__(
        self,
        script: Sequence[ApiDesignProposal | DesignProposalParsingError],
    ) -> None:
        self._script = list(script)
        self.received_tasks: list[ApiDesignTask] = []

    def propose(self, task: ApiDesignTask) -> ApiDesignProposal:
        self.received_tasks.append(task)
        result = self._script.pop(0)
        if isinstance(result, DesignProposalParsingError):
            raise result
        return result


def _service(
    designer: ScriptedApiDesigner, *, max_attempts: int = 2
) -> ApiGenerationService:
    return ApiGenerationService(
        designer=designer,
        validator=ApiDesignValidator(),
        max_attempts=max_attempts,
    )


def test_api_generation_succeeds_on_first_valid_proposal() -> None:
    designer = ScriptedApiDesigner([_proposal(_api_design())])

    result: ApiGenerationResult = _service(designer).generate(_scenario(), _graph(), {})

    assert result.status is GenerationStatus.SUCCEEDED
    assert result.api_design is not None
    assert len(result.attempts) == 1
    assert designer.received_tasks[0].mode is DesignTaskMode.INITIAL


def test_api_validation_failure_builds_repair_task() -> None:
    designer = ScriptedApiDesigner(
        [
            _proposal(_api_design(handler_component_id="missing_component")),
            _proposal(_api_design()),
        ]
    )

    result: ApiGenerationResult = _service(designer).generate(_scenario(), _graph(), {})

    assert result.status is GenerationStatus.SUCCEEDED
    assert len(result.attempts) == EXPECTED_RESULT_ATTEMPTS_COUNT
    repair_task = designer.received_tasks[1]
    assert repair_task.mode is DesignTaskMode.REPAIR
    assert repair_task.previous_payload is not None
    assert repair_task.validation_feedback
    assert any(
        feedback.error_code == "NON_EXISTENT_COMPONENT_REFERENCE"
        for feedback in repair_task.validation_feedback
    )


def test_api_parsing_failure_builds_repair_task() -> None:
    parsing_error = DesignProposalParsingError(
        raw_content="{ invalid json",
        failure_details=[
            ProposalFailureDetail(
                location="operations",
                message="Invalid JSON response",
                error_type="json_decode",
            )
        ],
        usage=TokenUsage(prompt_tokens=7, completion_tokens=3),
    )
    designer = ScriptedApiDesigner([parsing_error, _proposal(_api_design())])

    result: ApiGenerationResult = _service(designer).generate(_scenario(), _graph(), {})

    assert result.status is GenerationStatus.SUCCEEDED
    assert len(result.attempts) == EXPECTED_RESULT_ATTEMPTS_COUNT
    repair_task = designer.received_tasks[1]
    assert repair_task.mode is DesignTaskMode.REPAIR
    assert repair_task.previous_payload == parsing_error.raw_content
    assert (
        repair_task.parsing_failures == parsing_error.failure_details
    )
    assert (
        result.total_usage.total_tokens == EXPECTED_TOTAL_TOKENS
    )


def test_api_generation_returns_failure_after_max_attempts() -> None:
    invalid = _proposal(_api_design(handler_component_id="missing_component"))
    designer = ScriptedApiDesigner([invalid, invalid])

    result: ApiGenerationResult = _service(designer, max_attempts=2).generate(
        _scenario(), _graph(), {}
    )

    assert result.status is GenerationStatus.VALIDATION_FAILED
    assert result.api_design is None
    assert len(result.attempts) == EXPECTED_RESULT_ATTEMPTS_COUNT
    assert designer.received_tasks[-1].mode is DesignTaskMode.REPAIR

