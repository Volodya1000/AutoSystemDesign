# Copyright (c) 2026 Volodya1000
"""Domain specification validator for REST API Design models."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from domain.exceptions.architecture_errors import (
    ArchitectureValidationError,
    DuplicateOperationIdError,
    MissingPathParameterError,
    NonExistentComponentReferenceError,
    NonExistentRequirementReferenceError,
    PathCollisionError,
    UndeclaredPathParameterError,
    UnresolvedSchemaReferenceError,
)
from domain.models.api import ApiDesign, ApiOperation, ParameterLocation
from domain.specifications.interfaces import ValidationResult

if TYPE_CHECKING:
    from collections.abc import Set as AbstractSet

    from domain.models.topology import ArchitectureGraph

_PATH_VARIABLE_PATTERN: re.Pattern[str] = re.compile(r"\{([^}]+)\}")


def normalize_path_template(path: str) -> str:
    """Replace path variable names with empty placeholders to identify collisions.

    For example, '/v1/users/{id}' and '/v1/users/{userId}' both normalize
    to '/v1/users/{}', which represents a path collision per OpenAPI specifications.
    """
    return _PATH_VARIABLE_PATTERN.sub("{}", path).rstrip("/")


class ApiDesignValidator:
    """Validates structural and semantic invariants of an ApiDesign instance."""

    def validate(
        self,
        api: ApiDesign,
        graph: ArchitectureGraph,
        expected_requirement_ids: AbstractSet[str],
    ) -> ValidationResult:
        errors: list[ArchitectureValidationError] = []
        valid_node_ids: set[str] = {node.identifier for node in graph.nodes}
        available_schemas: set[str] = set(api.schemas.keys())

        errors.extend(self._validate_routes_and_identifiers(api.operations))
        errors.extend(self._validate_path_parameters(api.operations))
        errors.extend(self._validate_schema_refs(api.operations, available_schemas))
        errors.extend(self._validate_component_linkage(api.operations, valid_node_ids))
        errors.extend(
            self._validate_requirements(api.operations, expected_requirement_ids)
        )

        return ValidationResult(errors=errors)

    def _validate_routes_and_identifiers(
        self, operations: list[ApiOperation]
    ) -> list[ArchitectureValidationError]:
        errors: list[ArchitectureValidationError] = []
        seen_operation_ids: set[str] = set()
        seen_route_signatures: set[tuple[str, str]] = set()

        for op in operations:
            if op.operation_id in seen_operation_ids:
                errors.append(DuplicateOperationIdError(operation_id=op.operation_id))
            seen_operation_ids.add(op.operation_id)

            normalized_path: str = normalize_path_template(op.path)
            route_signature: tuple[str, str] = (op.method.value, normalized_path)
            if route_signature in seen_route_signatures:
                errors.append(
                    PathCollisionError(
                        method=op.method.value,
                        path=op.path,
                        normalized_path=normalized_path,
                    )
                )
            seen_route_signatures.add(route_signature)

        return errors

    def _validate_path_parameters(
        self, operations: list[ApiOperation]
    ) -> list[ArchitectureValidationError]:
        errors: list[ArchitectureValidationError] = []

        for op in operations:
            url_variables: set[str] = set(_PATH_VARIABLE_PATTERN.findall(op.path))
            declared_params: set[str] = {
                p.name for p in op.parameters if p.in_location is ParameterLocation.PATH
            }

            missing = url_variables - declared_params
            if missing:
                errors.append(
                    MissingPathParameterError(
                        operation_id=op.operation_id,
                        missing_parameters=sorted(missing),
                    )
                )

            undeclared = declared_params - url_variables
            if undeclared:
                errors.append(
                    UndeclaredPathParameterError(
                        operation_id=op.operation_id,
                        undeclared_parameters=sorted(undeclared),
                    )
                )

        return errors

    def _validate_schema_refs(
        self, operations: list[ApiOperation], available_schemas: set[str]
    ) -> list[ArchitectureValidationError]:
        errors: list[ArchitectureValidationError] = []

        for op in operations:
            if (
                op.request_body
                and op.request_body.schema_ref
                and op.request_body.schema_ref not in available_schemas
            ):
                errors.append(
                    UnresolvedSchemaReferenceError(
                        operation_id=op.operation_id,
                        target="request_body",
                        missing_schema_ref=op.request_body.schema_ref,
                    )
                )

            errors.extend(
                UnresolvedSchemaReferenceError(
                    operation_id=op.operation_id,
                    target=f"response_{resp.status_code}",
                    missing_schema_ref=resp.schema_ref,
                )
                for resp in op.responses
                if resp.schema_ref and resp.schema_ref not in available_schemas
            )

        return errors

    def _validate_component_linkage(
        self, operations: list[ApiOperation], valid_node_ids: set[str]
    ) -> list[ArchitectureValidationError]:
        errors: list[ArchitectureValidationError] = []

        for op in operations:
            if op.entrypoint_component_id not in valid_node_ids:
                errors.append(
                    NonExistentComponentReferenceError(
                        operation_id=op.operation_id,
                        role="entrypoint_component_id",
                        component_id=op.entrypoint_component_id,
                    )
                )
            if op.handler_component_id not in valid_node_ids:
                errors.append(
                    NonExistentComponentReferenceError(
                        operation_id=op.operation_id,
                        role="handler_component_id",
                        component_id=op.handler_component_id,
                    )
                )

        return errors

    def _validate_requirements(
        self, operations: list[ApiOperation], expected_requirement_ids: AbstractSet[str]
    ) -> list[ArchitectureValidationError]:
        if not expected_requirement_ids:
            return []

        return [
            NonExistentRequirementReferenceError(
                operation_id=op.operation_id,
                requirement_id=req_id,
            )
            for op in operations
            for req_id in op.requirement_ids
            if req_id not in expected_requirement_ids
        ]
