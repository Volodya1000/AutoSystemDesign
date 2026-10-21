# Copyright (c) 2026 Volodya1000
"""Unit tests of the DesignGenerationService ScenarioValidator port.

These exercise the port independently of the main DesignGenerationService
suite: fake designers, fake topology validators, fake scenario validators,
no LLM. Extracted from the old tests/integration/test_design_generation_pipeline.py,
which despite living under integration/ was marked pytest.mark.unit and
never touched the network.
"""

from collections.abc import Sequence

import pytest

from application.results import DesignGenerationResult, GenerationStatus
from application.services.design_generation_service import DesignGenerationService
from application.tasks import DesignProposal, DesignTask, DesignTaskMode
from application.usage import TokenUsage
from domain.exceptions.architecture_errors import ArchitectureValidationError
from domain.models import DesignScenario, WorkloadProfile
from domain.models.enums import NodeType
from domain.models.topology import ArchitectureGraph
from domain.specifications.interfaces import (
    BaseValidator,
    ScenarioValidator,
    ValidationResult,
)
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
        del graph
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
