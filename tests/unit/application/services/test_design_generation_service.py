# Copyright (c) 2026 Volodya1000
"""Unit tests of the DesignGenerationService repair loop."""

from collections.abc import Sequence

import pytest

from application.exceptions.configuration_errors import GenerationConfigurationError
from application.exceptions.generation_exceptions import DesignProposalParsingError
from application.results import DesignGenerationResult, GenerationStatus
from application.services.design_generation_service import DesignGenerationService
from application.tasks import (
    JSON_DECODE_ERROR_TYPE,
    DesignProposal,
    DesignTask,
    DesignTaskMode,
    ProposalFailureDetail,
)
from application.usage import TokenUsage
from domain.exceptions.architecture_errors import IsolatedNodeError
from domain.models import DesignScenario
from domain.models.enums import NodeType
from domain.models.topology import ArchitectureGraph
from domain.specifications.structural_validator import StructuralTopologyValidator
from tests.factories import create_test_edge, create_test_node

pytestmark = pytest.mark.unit


def _valid_graph() -> ArchitectureGraph:
    return ArchitectureGraph(
        nodes=[
            create_test_node("client_1", NodeType.CLIENT),
            create_test_node("compute_1", NodeType.COMPUTE),
            create_test_node("db_1", NodeType.DATABASE),
        ],
        edges=[
            create_test_edge("client_1", "compute_1"),
            create_test_edge("compute_1", "db_1"),
        ],
    )


def _isolated_graph() -> ArchitectureGraph:
    return ArchitectureGraph(
        nodes=[
            create_test_node("client_1", NodeType.CLIENT),
            create_test_node("compute_1", NodeType.COMPUTE),
            create_test_node("db_orphan", NodeType.DATABASE),
        ],
        edges=[create_test_edge("client_1", "compute_1")],
    )


def _proposal(
    graph: ArchitectureGraph,
    prompt_tokens: int,
    completion_tokens: int,
    latency_seconds: float = 0.0,
) -> DesignProposal:
    return DesignProposal(
        graph=graph,
        raw_content="raw content",
        usage=TokenUsage(
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
        ),
        latency_seconds=latency_seconds,
    )


def _parsing_failure(prompt_tokens: int) -> DesignProposalParsingError:
    return DesignProposalParsingError(
        raw_content="not json",
        failure_details=[
            ProposalFailureDetail(
                location="$", message="broken", error_type=JSON_DECODE_ERROR_TYPE
            )
        ],
        usage=TokenUsage(prompt_tokens=prompt_tokens, completion_tokens=1),
    )


class UnexpectedExtraProposalError(AssertionError):
    """The service requested more proposals than the test scripted."""

    def __init__(self) -> None:
        super().__init__("Unexpected extra propose() call")


class FakeDesigner:
    """Scripted designer recording every task it receives."""

    def __init__(
        self, script: Sequence[DesignProposal | DesignProposalParsingError]
    ) -> None:
        self._script: list[DesignProposal | DesignProposalParsingError] = list(script)
        self.received_tasks: list[DesignTask] = []

    def propose(self, task: DesignTask) -> DesignProposal:
        self.received_tasks.append(task)
        if not self._script:
            raise UnexpectedExtraProposalError
        item: DesignProposal | DesignProposalParsingError = self._script.pop(0)
        if isinstance(item, DesignProposalParsingError):
            raise item
        return item


def _build_service(
    script: Sequence[DesignProposal | DesignProposalParsingError],
    max_attempts: int = 3,
) -> tuple[DesignGenerationService, FakeDesigner]:
    designer: FakeDesigner = FakeDesigner(script)
    service: DesignGenerationService = DesignGenerationService(
        designer=designer,
        validators=[StructuralTopologyValidator()],
        max_attempts=max_attempts,
    )
    return service, designer


class TestDesignGenerationService:
    @staticmethod
    def test_immediate_success(scenario: DesignScenario) -> None:
        service, designer = _build_service([_proposal(_valid_graph(), 100, 50, 5.0)])
        result: DesignGenerationResult = service.generate(scenario)
        assert result.status is GenerationStatus.SUCCEEDED
        assert len(result.attempts) == 1
        assert result.attempts[0].validation is not None
        assert result.attempts[0].validation.is_successful
        assert result.attempts[0].latency_seconds == 5.0
        assert result.graph is result.attempts[0].payload
        assert result.total_usage == TokenUsage(prompt_tokens=100, completion_tokens=50)
        assert len(designer.received_tasks) == 1

    @staticmethod
    def test_repair_after_structural_violation(scenario: DesignScenario) -> None:
        service, designer = _build_service(
            [_proposal(_isolated_graph(), 100, 50), _proposal(_valid_graph(), 200, 60)]
        )
        result: DesignGenerationResult = service.generate(scenario)
        assert result.status is GenerationStatus.SUCCEEDED
        assert len(result.attempts) == 2
        assert result.attempts[0].validation is not None
        assert result.attempts[0].validation.has_error(IsolatedNodeError)
        first_graph: ArchitectureGraph | None = result.attempts[0].payload
        assert first_graph is not None
        repair_task: DesignTask = designer.received_tasks[1]
        assert repair_task.mode is DesignTaskMode.REPAIR
        assert repair_task.previous_graph_payload == first_graph.model_dump_json()
        assert any(
            feedback.error_code == "ISOLATED_NODE"
            for feedback in repair_task.validation_feedback
        )
        assert repair_task.parsing_failures == []

    @staticmethod
    def test_repair_after_parsing_failure(scenario: DesignScenario) -> None:
        parsing_failure: DesignProposalParsingError = _parsing_failure(prompt_tokens=90)
        service, designer = _build_service(
            [parsing_failure, _proposal(_valid_graph(), 100, 50)]
        )
        result: DesignGenerationResult = service.generate(scenario)
        assert result.status is GenerationStatus.SUCCEEDED
        first_attempt = result.attempts[0]
        assert first_attempt.parsed is False
        assert first_attempt.payload is None
        assert first_attempt.validation is None
        assert first_attempt.usage.prompt_tokens == 90
        assert first_attempt.parsing_failures == parsing_failure.failure_details
        repair_task: DesignTask = designer.received_tasks[1]
        assert repair_task.mode is DesignTaskMode.REPAIR
        assert repair_task.previous_graph_payload == "not json"
        assert repair_task.parsing_failures == parsing_failure.failure_details
        assert repair_task.validation_feedback == []

    @staticmethod
    def test_all_attempts_structurally_invalid(scenario: DesignScenario) -> None:
        service, _ = _build_service([_proposal(_isolated_graph(), 10, 5)] * 3)
        result: DesignGenerationResult = service.generate(scenario)
        assert result.status is GenerationStatus.VALIDATION_FAILED
        assert len(result.attempts) == 3
        assert result.graph is not None

    @staticmethod
    def test_all_attempts_unparseable(scenario: DesignScenario) -> None:
        service, _ = _build_service([_parsing_failure(prompt_tokens=10)] * 3)
        result: DesignGenerationResult = service.generate(scenario)
        assert result.status is GenerationStatus.PARSING_FAILED
        assert result.graph is None
        assert all(not attempt.parsed for attempt in result.attempts)

    @staticmethod
    def test_total_usage_aggregates_across_attempts(
        scenario: DesignScenario
    ) -> None:
        service, _ = _build_service(
            [
                _parsing_failure(prompt_tokens=10),
                _proposal(_isolated_graph(), 100, 50),
                _proposal(_valid_graph(), 200, 60),
            ]
        )
        result: DesignGenerationResult = service.generate(scenario)
        assert result.total_usage == TokenUsage(
            prompt_tokens=310, completion_tokens=111
        )

    @staticmethod
    def test_multiple_validators_errors_are_aggregated(
        scenario: DesignScenario
    ) -> None:
        designer: FakeDesigner = FakeDesigner([_proposal(_isolated_graph(), 10, 5)])
        service: DesignGenerationService = DesignGenerationService(
            designer=designer,
            validators=[StructuralTopologyValidator(), StructuralTopologyValidator()],
            max_attempts=1,
        )
        result: DesignGenerationResult = service.generate(scenario)
        assert result.status is GenerationStatus.VALIDATION_FAILED
        assert result.attempts[0].validation is not None
        isolated_errors = [
            error
            for error in result.attempts[0].validation.errors
            if isinstance(error, IsolatedNodeError)
        ]
        assert len(isolated_errors) == 2  # one per validator

    @staticmethod
    def test_empty_validators_are_rejected() -> None:
        with pytest.raises(
            GenerationConfigurationError, match="At least one validator is required"
        ):
            DesignGenerationService(
                designer=FakeDesigner([]),
                validators=[],
                max_attempts=3,
            )

    @staticmethod
    def test_max_attempts_bounds_are_enforced() -> None:
        with pytest.raises(
            GenerationConfigurationError, match="max_attempts must be between"
        ):
            DesignGenerationService(
                designer=FakeDesigner([]),
                validators=[StructuralTopologyValidator()],
                max_attempts=0,
            )
        with pytest.raises(
            GenerationConfigurationError, match="max_attempts must be between"
        ):
            DesignGenerationService(
                designer=FakeDesigner([]),
                validators=[StructuralTopologyValidator()],
                max_attempts=11,
            )
