"""Unit tests of the DesignGenerationResult derived state."""

import pytest
from pydantic import ValidationError

from application.results import (
    DesignGenerationResult,
    GenerationAttempt,
    GenerationStatus,
)
from application.usage import TokenUsage
from domain.exceptions.architecture_errors import IsolatedNodeError
from domain.models.enums import NodeType
from domain.models.topology import ArchitectureGraph
from domain.specifications.interfaces import ValidationResult
from tests.unit.test_structural_validator import create_test_node

pytestmark = pytest.mark.unit


def _graph(identifier: str) -> ArchitectureGraph:
    return ArchitectureGraph(
        nodes=[create_test_node(identifier, NodeType.COMPUTE)], edges=[]
    )


def _attempt(
    parsed: bool,
    successful: bool | None,
    graph: ArchitectureGraph | None = None,
    attempt_number: int = 1,
) -> GenerationAttempt:
    validation: ValidationResult | None = None
    if successful is not None:
        validation = ValidationResult(
            errors=[] if successful else [IsolatedNodeError("x")]
        )
    return GenerationAttempt(
        attempt_number=attempt_number,
        parsed=parsed,
        graph=graph,
        validation=validation,
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1),
    )


class TestGenerationResultStatus:
    def test_succeeded_when_last_attempt_is_valid(self) -> None:
        result: DesignGenerationResult = DesignGenerationResult(
            attempts=[_attempt(True, True, graph=_graph("a"))]
        )
        assert result.status is GenerationStatus.SUCCEEDED

    def test_validation_failed_when_last_attempt_is_invalid(self) -> None:
        result: DesignGenerationResult = DesignGenerationResult(
            attempts=[_attempt(True, False, graph=_graph("a"))]
        )
        assert result.status is GenerationStatus.VALIDATION_FAILED

    def test_parsing_failed_when_last_attempt_is_unparseable(self) -> None:
        result: DesignGenerationResult = DesignGenerationResult(
            attempts=[_attempt(False, None)]
        )
        assert result.status is GenerationStatus.PARSING_FAILED

    def test_status_reflects_only_the_last_attempt(self) -> None:
        result: DesignGenerationResult = DesignGenerationResult(
            attempts=[
                _attempt(True, True, graph=_graph("a"), attempt_number=1),
                _attempt(False, None, attempt_number=2),
            ]
        )
        assert result.status is GenerationStatus.PARSING_FAILED

    def test_graph_returns_last_parsed_graph(self) -> None:
        first: ArchitectureGraph = _graph("node_a")
        second: ArchitectureGraph = _graph("node_b")
        result: DesignGenerationResult = DesignGenerationResult(
            attempts=[
                _attempt(True, False, graph=first, attempt_number=1),
                _attempt(True, True, graph=second, attempt_number=2),
            ]
        )
        assert result.graph is second

    def test_graph_is_none_when_never_parsed(self) -> None:
        result: DesignGenerationResult = DesignGenerationResult(
            attempts=[_attempt(False, None)]
        )
        assert result.graph is None

    def test_total_usage_aggregates_attempts(self) -> None:
        result: DesignGenerationResult = DesignGenerationResult(
            attempts=[
                _attempt(True, True, graph=_graph("a"), attempt_number=1),
                _attempt(False, None, attempt_number=2),
            ]
        )
        assert result.total_usage == TokenUsage(prompt_tokens=2, completion_tokens=2)

    def test_rejects_empty_attempts(self) -> None:
        with pytest.raises(ValidationError):
            DesignGenerationResult(attempts=[])
