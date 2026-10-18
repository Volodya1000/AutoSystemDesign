"""Edge-case tests for internal OpenAPI JSON Reference expansion."""

from copy import deepcopy

import pytest

from infrastructure.visualisation.openapi.dereference import dereference_internal_refs

pytestmark = pytest.mark.unit


def test_dereferences_nested_schemas_without_mutating_source() -> None:
    source = {
        "openapi": "3.1.0",
        "components": {
            "schemas": {
                "Resource": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}},
                },
                "Envelope": {
                    "type": "object",
                    "properties": {
                        "resource": {"$ref": "#/components/schemas/Resource"}
                    },
                },
            }
        },
        "paths": {
            "/resources": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Envelope"}
                                }
                            },
                        }
                    }
                }
            }
        },
    }
    original = deepcopy(source)

    result = dereference_internal_refs(source)

    schema = result["paths"]["/resources"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert schema["properties"]["resource"]["properties"]["id"] == {"type": "string"}
    assert "$ref" not in schema
    assert source == original
    assert result is not source


def test_decodes_json_pointer_escaped_slash_and_tilde() -> None:
    source = {
        "components": {
            "schemas": {
                "Thing/One~More": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                }
            }
        },
        "example": {"$ref": "#/components/schemas/Thing~1One~0More"},
    }

    result = dereference_internal_refs(source)

    example = result["example"]
    assert isinstance(example, dict)
    assert example == source["components"]["schemas"]["Thing/One~More"]
    assert "$ref" not in example


def test_resolves_json_pointer_array_indexes() -> None:
    source = {
        "catalog": [{"name": "first"}, {"name": "second"}],
        "example": {"$ref": "#/catalog/1"},
    }

    result = dereference_internal_refs(source)

    assert result["example"] == {"name": "second"}


def test_preserves_external_references() -> None:
    source = {
        "components": {
            "schemas": {"External": {"$ref": "https://schemas.example/resource.json"}}
        }
    }

    result = dereference_internal_refs(source)

    assert result == source


@pytest.mark.parametrize(
    "reference",
    [
        "#/components/schemas/DoesNotExist",
        "#missing-pointer",
        "#/components/schemas/../Resource",
    ],
)
def test_replaces_dangling_or_malformed_internal_references_with_diagnostic(
    reference: str,
) -> None:
    result = dereference_internal_refs({"value": {"$ref": reference}})

    value = result["value"]
    assert isinstance(value, dict)
    assert value["description"] == f"Unresolved reference: {reference}"
    assert "$ref" not in value


def test_collapses_recursive_schema_references_to_finite_stubs() -> None:
    source = {
        "components": {
            "schemas": {
                "Node": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "next": {"$ref": "#/components/schemas/Node"},
                    },
                }
            }
        },
        "root": {"$ref": "#/components/schemas/Node"},
    }

    result = dereference_internal_refs(source)

    root = result["root"]
    assert root["type"] == "object"
    assert root["properties"]["next"]["type"] == "object"
    assert (
        "Recursive reference"
        in root["properties"]["next"]["properties"]["next"]["description"]
    )
    assert "$ref" not in root
