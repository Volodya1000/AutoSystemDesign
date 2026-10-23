"""Exercise API references independently of rendered OpenAPI wording."""

import pytest

from domain.models.api import ApiDesign, ApiOperation, ApiResponse, HttpMethod
from domain.models.sequence import InteractionScenario
from domain.specifications.api_traceability import (
    ApiTraceabilityError,
    ApiTraceabilityValidator,
)
from domain.specifications.interfaces import ValidationResult
from tests.interaction_factories import create_test_interaction

pytestmark = pytest.mark.unit


def create_operation(
    requirement_ids: list[str], sequence_ids: list[str]
) -> ApiOperation:
    """Build an operation whose traceability is the subject of the test."""
    return ApiOperation(
        operation_id="create_order",
        method=HttpMethod.POST,
        path="/orders",
        summary="Create order",
        entrypoint_component_id="api",
        handler_component_id="api",
        requirement_ids=requirement_ids,
        sequence_ids=sequence_ids,
        responses=[ApiResponse(status_code="201", description="Created")],
    )


def _validate(
    operation: ApiOperation,
    sequences: list[InteractionScenario],
    expected: set[str] | None = None,
) -> ValidationResult:
    return ApiTraceabilityValidator().validate(
        ApiDesign(title="Orders", operations=[operation]),
        sequences,
        {"create"} if expected is None else expected,
    )


def test_operation_references_its_own_requirement_scenario() -> None:
    result: ValidationResult = _validate(
        create_operation(["create"], ["creation"]),
        [create_test_interaction("create", "creation")],
    )
    assert result.is_successful


@pytest.mark.parametrize(
    ("requirements", "identifiers"),
    [([], ["creation"]), (["create"], []), (["create"], ["unknown"])],
)
def test_missing_or_unknown_links_are_rejected(
    requirements: list[str], identifiers: list[str]
) -> None:
    result: ValidationResult = _validate(
        create_operation(requirements, identifiers),
        [create_test_interaction("create", "creation")],
    )
    assert result.has_error(ApiTraceabilityError)


def test_reference_to_another_requirements_scenario_is_rejected() -> None:
    result: ValidationResult = _validate(
        create_operation(["create"], ["status"]),
        [create_test_interaction("read", "status")],
    )
    assert result.has_error(ApiTraceabilityError)


def test_duplicate_scenario_id_is_ambiguous_even_if_one_requirement_matches() -> None:
    result: ValidationResult = _validate(
        create_operation(["create"], ["same"]),
        [
            create_test_interaction("create", "same"),
            create_test_interaction("read", "same"),
        ],
    )
    assert result.has_error(ApiTraceabilityError)


def test_uncovered_functional_requirement_is_rejected() -> None:
    result: ValidationResult = _validate(
        create_operation(["create"], ["creation"]),
        [create_test_interaction("create", "creation")],
        {"create", "read"},
    )
    assert result.has_error(ApiTraceabilityError)


def test_operation_can_implement_several_requirements_with_matching_scenarios() -> None:
    result: ValidationResult = _validate(
        create_operation(["create", "read"], ["creation", "status"]),
        [
            create_test_interaction("create", "creation"),
            create_test_interaction("read", "status"),
        ],
        {"create", "read"},
    )
    assert result.is_successful
