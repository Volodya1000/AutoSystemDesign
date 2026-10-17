"""Domain models for REST API Design specification."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApiModel(BaseModel):
    """Base model enforcing strictness and dual name/alias population across API entities."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_by_name=True,
        validate_by_alias=True,
    )


class HttpMethod(StrEnum):
    GET = "get"
    POST = "post"
    PUT = "put"
    PATCH = "patch"
    DELETE = "delete"


class DataType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


class ParameterLocation(StrEnum):
    PATH = "path"
    QUERY = "query"
    HEADER = "header"


class ApiParameter(ApiModel):
    name: str = Field(description="Parameter name, e.g. 'chatId' or 'tags'")
    in_location: ParameterLocation = Field(
        alias="in",
        description="Parameter location: path, query or header",
    )
    required: bool
    data_type: DataType
    item_type: DataType | None = Field(
        default=None,
        description="Required if data_type == 'array'. Defines the type of array items.",
    )
    format: str | None = Field(default=None, description="e.g. 'uuid', 'date-time'")
    description: str | None = None

    @model_validator(mode="after")
    def _validate_types(self) -> Self:
        if self.data_type == DataType.ARRAY and self.item_type is None:
            raise ValueError(
                f"Parameter '{self.name}' has data_type='array' but 'item_type' is not defined."
            )
        if self.data_type != DataType.ARRAY and self.item_type is not None:
            raise ValueError(
                f"Parameter '{self.name}' must not define 'item_type' when "
                f"data_type is '{self.data_type.value}'."
            )
        if self.in_location == ParameterLocation.PATH and not self.required:
            raise ValueError(
                f"Path parameter '{self.name}' must always have required=True."
            )
        return self


class ApiRequestBody(ApiModel):
    required: bool = True
    content_type: str = Field(default="application/json")
    schema_ref: str = Field(
        description="Name of the schema in the central registry (e.g., 'CreateOrderRequest')"
    )


_STATUS_CODE_PATTERN = re.compile(r"^[1-5][0-9]{2}$")


class ApiResponse(ApiModel):
    status_code: str = Field(
        description="HTTP status code (3 digits: '200', '201', '404') or 'default'"
    )
    description: str
    content_type: str | None = Field(default="application/json")
    schema_ref: str | None = Field(
        default=None,
        description="Name of the schema in the central registry (e.g., 'OrderResponse')",
    )

    @model_validator(mode="after")
    def _validate_status_code(self) -> Self:
        code = self.status_code.lower()
        if code != "default" and not _STATUS_CODE_PATTERN.match(code):
            raise ValueError(
                f"Invalid HTTP status code '{self.status_code}'. Must be 3-digit code or 'default'."
            )
        return self


class ApiOperation(ApiModel):
    operation_id: str = Field(
        description="Unique operation identifier, snake_case or camelCase"
    )
    method: HttpMethod
    path: str = Field(
        description="URL template path, e.g. '/v1/chats/{chatId}/messages'"
    )
    summary: str
    description: str | None = None

    entrypoint_component_id: str = Field(
        description="C4 Node ID accepting external traffic (e.g. 'edge_lb', 'api_gateway')"
    )
    handler_component_id: str = Field(
        description="C4 Node ID executing the operation (e.g. 'orders_api')"
    )

    requirement_ids: list[str] = Field(default_factory=list)
    sequence_ids: list[str] = Field(default_factory=list)

    parameters: list[ApiParameter] = Field(default_factory=list)
    request_body: ApiRequestBody | None = None
    responses: list[ApiResponse] = Field(min_length=1)

    security_required: bool = Field(
        default=False,
        description="If True, endpoint requires standard Bearer JWT authorization",
    )

    @model_validator(mode="after")
    def _validate_unique_responses(self) -> Self:
        seen = set()
        for resp in self.responses:
            if resp.status_code in seen:
                raise ValueError(
                    f"Duplicate response status code '{resp.status_code}' in "
                    f"operation '{self.operation_id}'."
                )
            seen.add(resp.status_code)
        return self


class ApiDesign(ApiModel):
    title: str
    version: str = "1.0.0"
    description: str | None = None

    schemas: dict[str, dict] = Field(
        default_factory=dict,
        description="Central registry of reusable JSON Schemas (DTOs)",
    )
    operations: list[ApiOperation] = Field(min_length=1)
