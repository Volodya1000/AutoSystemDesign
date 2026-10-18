"""Unit tests for semantic validation of generated API designs."""

import pytest

from domain.exceptions.architecture_errors import (
    DuplicateOperationIdError,
    MissingPathParameterError,
    NonExistentComponentReferenceError,
    NonExistentRequirementReferenceError,
    PathCollisionError,
    UndeclaredPathParameterError,
    UnresolvedSchemaReferenceError,
)
from domain.models.api import (
    ApiDesign,
    ApiOperation,
    ApiParameter,
    ApiRequestBody,
    ApiResponse,
    DataType,
    HttpMethod,
    ParameterLocation,
)
from domain.models.nodes import ComputeNode
from domain.models.topology import ArchitectureGraph
from domain.specifications.api_validator import ApiDesignValidator

pytestmark = pytest.mark.unit


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


def _operation(
    *,
    operation_id: str = "get_resource",
    method: HttpMethod = HttpMethod.GET,
    path: str = "/v1/resources",
    entrypoint: str = "api",
    handler: str = "api",
    requirement_ids: list[str] | None = None,
    parameters: list[ApiParameter] | None = None,
    request_body: ApiRequestBody | None = None,
    responses: list[ApiResponse] | None = None,
) -> ApiOperation:
    return ApiOperation(
        operation_id=operation_id,
        method=method,
        path=path,
        summary="Get resource",
        entrypoint_component_id=entrypoint,
        handler_component_id=handler,
        requirement_ids=requirement_ids or [],
        parameters=parameters or [],
        request_body=request_body,
        responses=responses or [ApiResponse(status_code="200", description="OK")],
    )


def _validate(
    operations: list[ApiOperation],
    *,
    schemas: dict[str, dict] | None = None,
    requirement_ids: set[str] | None = None,
):
    api = ApiDesign(title="Test API", operations=operations, schemas=schemas or {})
    return ApiDesignValidator().validate(
        api, _graph(), requirement_ids if requirement_ids is not None else {"FR-1"}
    )


def test_valid_api_design_has_no_validation_errors() -> None:
    result = _validate(
        [
            _operation(
                requirement_ids=["FR-1"],
                responses=[ApiResponse(status_code="200", description="OK")],
            )
        ]
    )

    assert result.is_successful


def test_duplicate_operation_ids_and_normalized_routes_are_rejected() -> None:
    result = _validate(
        [
            _operation(operation_id="get_resource", path="/v1/resources/{id}"),
            _operation(
                operation_id="get_resource",
                path="/v1/resources/{resource_id}",
            ),
        ]
    )

    assert result.has_error(DuplicateOperationIdError)
    assert result.has_error(PathCollisionError)


def test_missing_path_parameter_is_rejected() -> None:
    result = _validate([_operation(path="/v1/resources/{resource_id}")])

    assert result.has_error(MissingPathParameterError)


def test_path_parameter_not_present_in_route_is_rejected() -> None:
    result = _validate(
        [
            _operation(
                parameters=[
                    ApiParameter.model_validate(
                        {
                            "name": "resource_id",
                            "in": ParameterLocation.PATH.value,
                            "required": True,
                            "data_type": DataType.STRING.value,
                        }
                    )
                ]
            )
        ]
    )

    assert result.has_error(UndeclaredPathParameterError)


def test_unknown_request_and_response_schema_references_are_rejected() -> None:
    result = _validate(
        [
            _operation(
                request_body=ApiRequestBody(schema_ref="MissingRequest"),
                responses=[
                    ApiResponse(
                        status_code="201",
                        description="Created",
                        schema_ref="MissingResponse",
                    )
                ],
            )
        ]
    )

    assert result.has_error(UnresolvedSchemaReferenceError)
    assert (
        sum(
            isinstance(error, UnresolvedSchemaReferenceError) for error in result.errors
        )
        == 2
    )


def test_unknown_components_and_requirement_references_are_rejected() -> None:
    result = _validate(
        [
            _operation(
                entrypoint="missing_entrypoint",
                handler="missing_handler",
                requirement_ids=["FR-404"],
            )
        ]
    )

    assert result.has_error(NonExistentComponentReferenceError)
    assert result.has_error(NonExistentRequirementReferenceError)
