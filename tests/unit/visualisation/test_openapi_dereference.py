# Copyright (c) 2026 Volodya1000
"""Unit tests for internal-$ref dereferencing in the Swagger HTML artifact.

Covers: inlining at every usage site, cycle collapse (self-referential and
mutual), dangling and malformed pointers, $ref siblings (OpenAPI 3.1
sibling-wins semantics), traversal of lists/allOf, escaped JSON-Pointer
segments (~0/~1 per RFC 6901), root-pointer termination, non-object
targets, input purity, and self-containment of the rendered HTML page.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from infrastructure.visualisation.openapi.dereference import dereference_internal_refs
from infrastructure.visualisation.openapi.swagger_ui_renderer import SwaggerUiRenderer

if TYPE_CHECKING:
    import pytest


def _chat_spec() -> dict[str, Any]:
    """Create a small but realistic OpenAPI document with $refs in several places."""
    return {
        "openapi": "3.1.0",
        "info": {"title": "Chat", "version": "1.0.0"},
        "paths": {
            "/messages": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/SendMessage"}
                            }
                        }
                    },
                    "responses": {
                        "201": {
                            "description": "Created",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/SendMessage"
                                    }
                                }
                            },
                        }
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "SendMessage": {
                    "type": "object",
                    "properties": {"body": {"type": "string"}},
                    "required": ["body"],
                }
            }
        },
    }


class TestInlining:
    @staticmethod
    def test_inlines_refs_at_every_usage_site() -> None:
        result = dereference_internal_refs(_chat_spec())
        request_schema = result["paths"]["/messages"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]
        assert request_schema == {
            "type": "object",
            "properties": {"body": {"type": "string"}},
            "required": ["body"],
        }

    @staticmethod
    def test_no_ref_key_remains_in_output() -> None:
        assert "$ref" not in json.dumps(dereference_internal_refs(_chat_spec()))

    @staticmethod
    def test_repeated_usage_produces_independent_copies() -> None:
        result = dereference_internal_refs(_chat_spec())
        request_schema = result["paths"]["/messages"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]
        response_schema = result["paths"]["/messages"]["post"]["responses"]["201"][
            "content"
        ]["application/json"]["schema"]
        assert request_schema == response_schema
        assert request_schema is not response_schema


class TestCycles:
    @staticmethod
    def test_self_reference_collapses_to_stub() -> None:
        spec = {
            "components": {
                "schemas": {
                    "Node": {
                        "type": "object",
                        "properties": {
                            "children": {
                                "type": "array",
                                "items": {"$ref": "#/components/schemas/Node"},
                            }
                        },
                    }
                }
            }
        }
        result = dereference_internal_refs(spec)
        items = result["components"]["schemas"]["Node"]["properties"]["children"][
            "items"
        ]
        assert items["type"] == "object"
        nested_items = items["properties"]["children"]["items"]
        assert "Recursive" in nested_items["description"]
        assert "$ref" not in json.dumps(result)

    @staticmethod
    def test_mutual_cycle_collapses_to_stub() -> None:
        spec = {
            "components": {
                "schemas": {
                    "A": {
                        "type": "object",
                        "properties": {"b": {"$ref": "#/components/schemas/B"}},
                    },
                    "B": {
                        "type": "object",
                        "properties": {"a": {"$ref": "#/components/schemas/A"}},
                    },
                }
            }
        }
        result = dereference_internal_refs(spec)
        inner_a = result["components"]["schemas"]["B"]["properties"]["a"]
        assert inner_a["type"] == "object"
        inner_b = inner_a["properties"]["b"]
        assert "Recursive" in inner_b["properties"]["a"]["description"]

    @staticmethod
    def test_root_pointer_terminates() -> None:
        # "$ref": "#" points at the whole document; pathological input, but
        # it must not recurse forever.
        spec = {
            "info": {"version": "1.0.0"},
            "paths": {
                "/x": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "ok",
                                "content": {
                                    "application/json": {"schema": {"$ref": "#"}}
                                },
                            }
                        }
                    }
                }
            },
        }
        result = dereference_internal_refs(spec)
        assert "$ref" not in json.dumps(result)


class TestDanglingRefs:
    @staticmethod
    def test_missing_schema_becomes_descriptive_stub() -> None:
        spec = {
            "paths": {
                "/x": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "ok",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "$ref": "#/components/schemas/Missing"
                                        }
                                    }
                                },
                            }
                        }
                    }
                }
            }
        }
        schema = dereference_internal_refs(spec)["paths"]["/x"]["get"]["responses"][
            "200"
        ]["content"]["application/json"]["schema"]
        assert "Unresolved reference" in schema["description"]

    @staticmethod
    def test_malformed_pointer_becomes_stub() -> None:
        # "components" (no leading slash) is not a valid JSON pointer.
        spec = {"a": {"$ref": "#components"}}
        result = dereference_internal_refs(spec)
        assert "Unresolved reference" in result["a"]["description"]

    @staticmethod
    def test_pointer_to_absent_empty_key() -> None:
        # RFC 6901: "/" addresses the root key "" -- absent here, so the
        # reference resolves to a stub, not to the whole document.
        spec = {"a": {"$ref": "#/"}}
        result = dereference_internal_refs(spec)
        assert "Unresolved reference" in result["a"]["description"]


class TestRefSiblings:
    @staticmethod
    def test_sibling_overrides_target_field() -> None:
        spec = {
            "paths": {
                "/x": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "ok",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "$ref": "#/components/schemas/Foo",
                                            "description": "Sibling wins",
                                        }
                                    }
                                },
                            }
                        }
                    }
                }
            },
            "components": {
                "schemas": {
                    "Foo": {
                        "type": "object",
                        "description": "Target description",
                        "properties": {},
                    }
                }
            },
        }
        schema = dereference_internal_refs(spec)["paths"]["/x"]["get"]["responses"][
            "200"
        ]["content"]["application/json"]["schema"]
        assert schema == {
            "type": "object",
            "description": "Sibling wins",
            "properties": {},
        }

    @staticmethod
    def test_siblings_survive_on_unresolved_stub() -> None:
        # A sibling "description" would REPLACE the stub's diagnostic text
        # (sibling-wins semantics), so use a non-clashing sibling key here.
        spec = {"a": {"$ref": "#/components/schemas/Missing", "title": "Kept"}}
        result = dereference_internal_refs(spec)
        assert result["a"]["title"] == "Kept"
        assert "Unresolved reference" in result["a"]["description"]


class TestStructureTraversal:
    @staticmethod
    def test_refs_inside_arrays_and_allof_are_inlined() -> None:
        spec = {
            "components": {
                "schemas": {
                    "Foo": {"type": "object"},
                    "Bar": {"type": "string"},
                }
            },
            "schema": {
                "allOf": [
                    {"$ref": "#/components/schemas/Foo"},
                    {"$ref": "#/components/schemas/Bar"},
                ]
            },
        }
        result = dereference_internal_refs(spec)
        assert result["schema"]["allOf"][0] == {"type": "object"}
        assert result["schema"]["allOf"][1] == {"type": "string"}

    @staticmethod
    def test_escaped_pointer_segments_are_resolved() -> None:
        # RFC 6901: "~1" encodes "/", "~0" encodes "~" within a segment.
        spec = {
            "components": {
                "schemas": {
                    "Foo/Bar": {"type": "object"},
                    "Foo~Bar": {"type": "string"},
                }
            },
            "slash": {"$ref": "#/components/schemas/Foo~1Bar"},
            "tilde": {"$ref": "#/components/schemas/Foo~0Bar"},
        }
        result = dereference_internal_refs(spec)
        assert result["slash"] == {"type": "object"}
        assert result["tilde"] == {"type": "string"}

    @staticmethod
    def test_pointer_to_list_index() -> None:
        spec = {
            "a": {"$ref": "#/items/1"},
            "items": [{"type": "null"}, {"type": "boolean"}],
        }
        assert dereference_internal_refs(spec)["a"] == {"type": "boolean"}

    @staticmethod
    def test_external_refs_are_preserved_verbatim() -> None:
        spec = {"a": {"$ref": "other.yaml#/components/schemas/Foo"}}
        assert dereference_internal_refs(spec) == spec


class TestNonObjectTargets:
    @staticmethod
    def test_ref_to_scalar_returns_scalar() -> None:
        spec = {"info": {"version": "1.2.3"}, "a": {"$ref": "#/info/version"}}
        assert dereference_internal_refs(spec)["a"] == "1.2.3"

    @staticmethod
    def test_dropped_siblings_on_scalar_target_log_warning(
        caplog: pytest.LogCaptureFixture
    ) -> None:
        spec = {
            "info": {"version": "1.2.3"},
            "a": {"$ref": "#/info/version", "description": "dropped"},
        }
        with caplog.at_level(logging.WARNING):
            result = dereference_internal_refs(spec)
        assert result["a"] == "1.2.3"
        assert any("siblings" in message for message in caplog.messages)


class TestPurity:
    @staticmethod
    def test_input_document_is_not_mutated() -> None:
        spec = _chat_spec()
        before = json.dumps(spec, sort_keys=True)
        dereference_internal_refs(spec)
        assert json.dumps(spec, sort_keys=True) == before

    @staticmethod
    def test_aliased_nodes_become_independent_copies() -> None:
        inner = {"$ref": "#/components/schemas/Foo"}
        spec = {
            "components": {"schemas": {"Foo": {"type": "object"}}},
            "list": [inner, inner],
        }
        before = json.dumps(spec, sort_keys=True)
        result = dereference_internal_refs(spec)
        assert json.dumps(spec, sort_keys=True) == before
        first, second = result["list"]
        assert first == second == {"type": "object"}
        assert first is not second


class TestSwaggerUiRenderer:
    @staticmethod
    def test_html_is_self_contained() -> None:
        page = SwaggerUiRenderer().render_html(_chat_spec(), "Chat <API>")
        assert "spec: spec" in page  # inline spec, never url:
        assert '"$ref"' not in page  # fully dereferenced
        assert "&lt;API&gt;" in page  # title is HTML-escaped

    @staticmethod
    def test_html_embeds_spec_content() -> None:
        page = SwaggerUiRenderer().render_html(_chat_spec(), "Chat")
        assert '"openapi"' in page
        assert "SendMessage" in page

    @staticmethod
    def test_standalone_preset_is_guarded() -> None:
        # Pins the regression: a possibly-undefined global must never be
        # pushed into the presets array unconditionally.
        page = SwaggerUiRenderer().render_html(_chat_spec(), "Chat")
        assert "swagger-ui-standalone-preset.js" in page
        assert 'typeof SwaggerUIStandalonePreset !== "undefined"' in page
