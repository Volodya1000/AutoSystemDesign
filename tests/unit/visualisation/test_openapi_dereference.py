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

import pytest

from infrastructure.visualisation.openapi.renderer import (
    SwaggerUiRenderer,
    dereference_internal_refs,
)


def _chat_spec() -> dict:
    """A small but realistic OpenAPI document with $refs in several places."""
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
    def test_inlines_refs_at_every_usage_site(self) -> None:
        result = dereference_internal_refs(_chat_spec())
        request_schema = result["paths"]["/messages"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]
        assert request_schema == {
            "type": "object",
            "properties": {"body": {"type": "string"}},
            "required": ["body"],
        }

    def test_no_ref_key_remains_in_output(self) -> None:
        assert "$ref" not in json.dumps(dereference_internal_refs(_chat_spec()))

    def test_repeated_usage_produces_independent_copies(self) -> None:
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
    def test_self_reference_collapses_to_stub(self) -> None:
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
        assert "Recursive" in items["description"]
        assert "$ref" not in json.dumps(result)

    def test_mutual_cycle_collapses_to_stub(self) -> None:
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
        assert "Recursive" in inner_a["description"]

    def test_root_pointer_terminates(self) -> None:
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
    def test_missing_schema_becomes_descriptive_stub(self) -> None:
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

    def test_malformed_pointer_becomes_stub(self) -> None:
        # "components" (no leading slash) is not a valid JSON pointer.
        spec = {"a": {"$ref": "#components"}}
        result = dereference_internal_refs(spec)
        assert "Unresolved reference" in result["a"]["description"]

    def test_pointer_to_absent_empty_key(self) -> None:
        # RFC 6901: "/" addresses the root key "" -- absent here, so the
        # reference resolves to a stub, not to the whole document.
        spec = {"a": {"$ref": "#/"}}
        result = dereference_internal_refs(spec)
        assert "Unresolved reference" in result["a"]["description"]


class TestRefSiblings:
    def test_sibling_overrides_target_field(self) -> None:
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

    def test_siblings_survive_on_unresolved_stub(self) -> None:
        # A sibling "description" would REPLACE the stub's diagnostic text
        # (sibling-wins semantics), so use a non-clashing sibling key here.
        spec = {"a": {"$ref": "#/components/schemas/Missing", "title": "Kept"}}
        result = dereference_internal_refs(spec)
        assert result["a"]["title"] == "Kept"
        assert "Unresolved reference" in result["a"]["description"]


class TestStructureTraversal:
    def test_refs_inside_arrays_and_allof_are_inlined(self) -> None:
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

    def test_escaped_pointer_segments_are_resolved(self) -> None:
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

    def test_pointer_to_list_index(self) -> None:
        spec = {
            "a": {"$ref": "#/items/1"},
            "items": [{"type": "null"}, {"type": "boolean"}],
        }
        assert dereference_internal_refs(spec)["a"] == {"type": "boolean"}

    def test_external_refs_are_preserved_verbatim(self) -> None:
        spec = {"a": {"$ref": "other.yaml#/components/schemas/Foo"}}
        assert dereference_internal_refs(spec) == spec


class TestNonObjectTargets:
    def test_ref_to_scalar_returns_scalar(self) -> None:
        spec = {"info": {"version": "1.2.3"}, "a": {"$ref": "#/info/version"}}
        assert dereference_internal_refs(spec)["a"] == "1.2.3"

    def test_dropped_siblings_on_scalar_target_log_warning(
        self, caplog: pytest.LogCaptureFixture
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
    def test_input_document_is_not_mutated(self) -> None:
        spec = _chat_spec()
        before = json.dumps(spec, sort_keys=True)
        dereference_internal_refs(spec)
        assert json.dumps(spec, sort_keys=True) == before

    def test_aliased_nodes_become_independent_copies(self) -> None:
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
    def test_html_is_self_contained(self) -> None:
        page = SwaggerUiRenderer().render_html(_chat_spec(), "Chat <API>")
        assert "spec: spec" in page  # inline spec, never url:
        assert '"$ref"' not in page  # fully dereferenced
        assert "&lt;API&gt;" in page  # title is HTML-escaped

    def test_html_embeds_spec_content(self) -> None:
        page = SwaggerUiRenderer().render_html(_chat_spec(), "Chat")
        assert '"openapi"' in page
        assert "SendMessage" in page

    def test_standalone_preset_is_guarded(self) -> None:
        # Pins the regression: a possibly-undefined global must never be
        # pushed into the presets array unconditionally.
        page = SwaggerUiRenderer().render_html(_chat_spec(), "Chat")
        assert "swagger-ui-standalone-preset.js" in page
        assert 'typeof SwaggerUIStandalonePreset !== "undefined"' in page
