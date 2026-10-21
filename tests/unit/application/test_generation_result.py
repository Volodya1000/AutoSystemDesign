# Copyright (c) 2026 Volodya1000
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
from tests.factories import create_test_node

pytestmark = pytest.mark.unit


def _graph(identifier: str) -> ArchitectureGraph:
    return ArchitectureGraph(
        nodes=[create_test_node(identifier, NodeType.COMPUTE)], edges=[]
    )


def _attempt(
    *,
    parsed: bool,
    successful: bool | None,
    graph: ArchitectureGraph | None = None,
    attempt_number: int = 1,
) -> GenerationAttempt[ArchitectureGraph]:
    validation: ValidationResult | None = None
    if successful is not None:
        validation = ValidationResult(
            errors=[] if successful else [IsolatedNodeError("x")]
        )
    return GenerationAttempt[ArchitectureGraph](
        attempt_number=attempt_number,
        parsed=parsed,
        payload=graph,
        validation=validation,
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1),
    )


class TestGenerationResultStatus:
    @staticmethod
    def test_succeeded_when_last_attempt_is_valid() -> None:
        result: DesignGenerationResult = DesignGenerationResult(
            attempts=[_attempt(parsed=True, successful=True, graph=_graph("a"))]
        )
        assert result.status is GenerationStatus.SUCCEEDED

    @staticmethod
    def test_validation_failed_when_last_attempt_is_invalid() -> None:
        result: DesignGenerationResult = DesignGenerationResult(
            attempts=[_attempt(parsed=True, successful=False, graph=_graph("a"))]
        )
        assert result.status is GenerationStatus.VALIDATION_FAILED

    @staticmethod
    def test_parsing_failed_when_last_attempt_is_unparseable() -> None:
        result: DesignGenerationResult = DesignGenerationResult(
            attempts=[_attempt(parsed=False, successful=None)]
        )
        assert result.status is GenerationStatus.PARSING_FAILED

    @staticmethod
    def test_status_reflects_only_the_last_attempt() -> None:
        result: DesignGenerationResult = DesignGenerationResult(
            attempts=[
                _attempt(
                    parsed=True,
                    successful=True,
                    graph=_graph("a"),
                    attempt_number=1,
                ),
                _attempt(parsed=False, successful=None, attempt_number=2),
            ]
        )
        assert result.status is GenerationStatus.PARSING_FAILED

    @staticmethod
    def test_graph_returns_last_parsed_graph() -> None:
        first: ArchitectureGraph = _graph("node_a")
        second: ArchitectureGraph = _graph("node_b")
        result: DesignGenerationResult = DesignGenerationResult(
            attempts=[
                _attempt(
                    parsed=True,
                    successful=False,
                    graph=first,
                    attempt_number=1,
                ),
                _attempt(
                    parsed=True,
                    successful=True,
                    graph=second,
                    attempt_number=2,
                ),
            ]
        )
        assert result.graph is second

    @staticmethod
    def test_graph_is_none_when_never_parsed() -> None:
        result: DesignGenerationResult = DesignGenerationResult(
            attempts=[_attempt(parsed=False, successful=None)]
        )
        assert result.graph is None

    @staticmethod
    def test_total_usage_aggregates_attempts() -> None:
        result: DesignGenerationResult = DesignGenerationResult(
            attempts=[
                _attempt(
                    parsed=True,
                    successful=True,
                    graph=_graph("a"),
                    attempt_number=1,
                ),
                _attempt(parsed=False, successful=None, attempt_number=2),
            ]
        )
        assert result.total_usage == TokenUsage(prompt_tokens=2, completion_tokens=2)

    @staticmethod
    def test_rejects_empty_attempts() -> None:
        with pytest.raises(ValidationError):
            DesignGenerationResult(attempts=[])
