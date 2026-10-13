"""Unit tests of the DesignGenerationService repair loop (integration copy)."""

from collections.abc import Sequence

import pytest

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
from domain.exceptions.architecture_errors import (
    ArchitectureValidationError,
    IsolatedNodeError,
)
from domain.models import DesignScenario, WorkloadProfile
from domain.models.enums import NodeType
from domain.models.topology import ArchitectureGraph
from domain.specifications.interfaces import (
    BaseValidator,
    ScenarioValidator,
    ValidationResult,
)
from domain.specifications.structural_validator import StructuralTopologyValidator
from tests.unit.test_structural_validator import create_test_edge, create_test_node

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
            raise AssertionError("Unexpected extra propose() call")
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
        designer=designer,  # type: ignore[arg-type]
        validators=[StructuralTopologyValidator()],
        max_attempts=max_attempts,
    )
    return service, designer


# ---------------------------------------------------------------------------
# Scenario validator port: local fakes and helpers
# ---------------------------------------------------------------------------


class _FakeTopologyError(ArchitectureValidationError):
    error_code = "FAKE_TOPOLOGY_ERROR"


class _FakeScenarioError(ArchitectureValidationError):
    error_code = "FAKE_SCENARIO_ERROR"


class StubScenarioValidator(ScenarioValidator):
    """Fake scenario validator recording calls, returning preset errors."""

    def __init__(self, errors: Sequence[ArchitectureValidationError] = ()) -> None:
        self.errors = list(errors)
        self.call_count = 0
        self.received_graphs: list[ArchitectureGraph] = []
        self.received_scenarios: list[DesignScenario] = []

    def validate(
        self, graph: ArchitectureGraph, scenario: DesignScenario
    ) -> ValidationResult:
        self.call_count += 1
        self.received_graphs.append(graph)
        self.received_scenarios.append(scenario)
        return ValidationResult(errors=list(self.errors))


class _ScenarioTopologyValidatorStub(BaseValidator):
    """Fake topology validator returning preset errors."""

    def __init__(self, errors: Sequence[ArchitectureValidationError] = ()) -> None:
        self.errors = list(errors)

    def validate(self, graph: ArchitectureGraph) -> ValidationResult:
        return ValidationResult(errors=list(self.errors))


class _ScenarioDesignerStub:
    """Fake designer returning one preset graph, recording received tasks."""

    def __init__(self, graph: ArchitectureGraph) -> None:
        self._graph = graph
        self.received_tasks: list[DesignTask] = []

    def propose(self, task: DesignTask) -> DesignProposal:
        self.received_tasks.append(task)
        return DesignProposal(
            graph=self._graph,
            raw_content="{}",
            usage=TokenUsage(),
        )


def _port_test_scenario() -> DesignScenario:
    """Minimal scenario for the scenario validator port tests."""
    return DesignScenario(
        identifier="test_scenario",
        description="Minimal scenario exercising the ScenarioValidator port",
        workload=WorkloadProfile(
            baseline_requests_per_second=10.0,
            peak_requests_per_second=20.0,
        ),
        requirements=[],
    )


class TestDesignGenerationService:
    def test_immediate_success(self, scenario: DesignScenario) -> None:
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

    def test_repair_after_structural_violation(self, scenario: DesignScenario) -> None:
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

    def test_repair_after_parsing_failure(self, scenario: DesignScenario) -> None:
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

    def test_all_attempts_structurally_invalid(self, scenario: DesignScenario) -> None:
        service, _ = _build_service([_proposal(_isolated_graph(), 10, 5)] * 3)
        result: DesignGenerationResult = service.generate(scenario)
        assert result.status is GenerationStatus.VALIDATION_FAILED
        assert len(result.attempts) == 3
        assert result.graph is not None

    def test_all_attempts_unparseable(self, scenario: DesignScenario) -> None:
        service, _ = _build_service([_parsing_failure(prompt_tokens=10)] * 3)
        result: DesignGenerationResult = service.generate(scenario)
        assert result.status is GenerationStatus.PARSING_FAILED
        assert result.graph is None
        assert all(not attempt.parsed for attempt in result.attempts)

    def test_total_usage_aggregates_across_attempts(
        self, scenario: DesignScenario
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

    def test_multiple_validators_errors_are_aggregated(
        self, scenario: DesignScenario
    ) -> None:
        designer: FakeDesigner = FakeDesigner([_proposal(_isolated_graph(), 10, 5)])
        service: DesignGenerationService = DesignGenerationService(
            designer=designer,  # type: ignore[arg-type]
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

    def test_empty_validators_are_rejected(self) -> None:
        with pytest.raises(ValueError):
            DesignGenerationService(
                designer=FakeDesigner([]),  # type: ignore[arg-type]
                validators=[],
                max_attempts=3,
            )

    def test_max_attempts_bounds_are_enforced(self) -> None:
        with pytest.raises(ValueError):
            DesignGenerationService(
                designer=FakeDesigner([]),  # type: ignore[arg-type]
                validators=[StructuralTopologyValidator()],
                max_attempts=0,
            )
        with pytest.raises(ValueError):
            DesignGenerationService(
                designer=FakeDesigner([]),  # type: ignore[arg-type]
                validators=[StructuralTopologyValidator()],
                max_attempts=11,
            )


# ---------------------------------------------------------------------------
# Scenario validator port tests
# ---------------------------------------------------------------------------


def test_scenario_validator_receives_graph_and_scenario() -> None:
    scenario: DesignScenario = _port_test_scenario()
    graph: ArchitectureGraph = _valid_graph()
    scenario_validator = StubScenarioValidator()
    service = DesignGenerationService(
        designer=_ScenarioDesignerStub(graph),
        validators=[_ScenarioTopologyValidatorStub()],
        max_attempts=1,
        scenario_validators=[scenario_validator],
    )

    result: DesignGenerationResult = service.generate(scenario)

    assert result.status is GenerationStatus.SUCCEEDED
    assert scenario_validator.call_count == 1
    assert scenario_validator.received_scenarios == [scenario]
    assert scenario_validator.received_scenarios[0] is scenario
    assert scenario_validator.received_graphs == [graph]


def test_scenario_and_topology_errors_are_aggregated_in_order() -> None:
    service = DesignGenerationService(
        designer=_ScenarioDesignerStub(_valid_graph()),
        validators=[
            _ScenarioTopologyValidatorStub(
                [_FakeTopologyError("fake topology failure")]
            )
        ],
        max_attempts=1,
        scenario_validators=[
            StubScenarioValidator([_FakeScenarioError("fake scenario failure")])
        ],
    )

    result: DesignGenerationResult = service.generate(_port_test_scenario())

    assert result.status is GenerationStatus.VALIDATION_FAILED
    validation = result.attempts[0].validation
    assert validation is not None
    assert len(validation.errors) == 2
    assert validation.is_successful is False
    assert [error.error_code for error in validation.errors] == [
        "FAKE_TOPOLOGY_ERROR",
        "FAKE_SCENARIO_ERROR",
    ]


def test_scenario_validators_run_even_when_topology_validation_fails() -> None:
    scenario_validator = StubScenarioValidator(
        [_FakeScenarioError("fake scenario failure")]
    )
    service = DesignGenerationService(
        designer=_ScenarioDesignerStub(_valid_graph()),
        validators=[
            _ScenarioTopologyValidatorStub(
                [_FakeTopologyError("fake topology failure")]
            )
        ],
        max_attempts=1,
        scenario_validators=[scenario_validator],
    )

    result: DesignGenerationResult = service.generate(_port_test_scenario())

    validation = result.attempts[0].validation
    assert validation is not None
    assert scenario_validator.call_count == 1
    assert [error.error_code for error in validation.errors] == [
        "FAKE_TOPOLOGY_ERROR",
        "FAKE_SCENARIO_ERROR",
    ]


def test_scenario_validator_failure_drives_repair_feedback() -> None:
    designer = _ScenarioDesignerStub(_valid_graph())
    service = DesignGenerationService(
        designer=designer,
        validators=[_ScenarioTopologyValidatorStub()],
        max_attempts=2,
        scenario_validators=[
            StubScenarioValidator([_FakeScenarioError("fake scenario failure")])
        ],
    )

    result: DesignGenerationResult = service.generate(_port_test_scenario())

    assert len(result.attempts) == 2
    for attempt in result.attempts:
        assert attempt.validation is not None
        assert [error.error_code for error in attempt.validation.errors] == [
            "FAKE_SCENARIO_ERROR"
        ]
    repair_task: DesignTask = designer.received_tasks[1]
    assert repair_task.mode is DesignTaskMode.REPAIR
    assert [fb.error_code for fb in repair_task.validation_feedback] == [
        "FAKE_SCENARIO_ERROR"
    ]


def test_scenario_validators_default_empty_keeps_old_behaviour() -> None:
    service = DesignGenerationService(
        designer=_ScenarioDesignerStub(_valid_graph()),
        validators=[_ScenarioTopologyValidatorStub()],
        max_attempts=1,
    )

    result: DesignGenerationResult = service.generate(_port_test_scenario())

    assert result.status is GenerationStatus.SUCCEEDED
