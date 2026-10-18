"""Deterministic renderer from ApiDesign to OpenAPI 3.1.0 JSON and Swagger HTML.

Two artifacts are derived from one ApiDesign:

* ``*_openapi.json``: the canonical OpenAPI document. Internal ``$ref``
  pointers are kept there on purpose -- they are a standard OpenAPI feature
  and every compliant tool resolves them.
* ``*_swagger.html``: a self-contained Swagger UI viewer. It embeds a fully
  dereferenced copy of the specification so that the page works when opened
  directly from the file system (``file://``); see
  ``dereference_internal_refs`` for the reason.
"""

from __future__ import annotations

import html
import json
import logging
from typing import Any

from domain.models.api import ApiDesign, ApiParameter, DataType

_logger: logging.Logger = logging.getLogger(__name__)


def safe_json_for_script(data: dict) -> str:
    """Escapes JSON string to be safely embedded inside HTML script tags."""
    return (
        json.dumps(data, indent=None)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


# ---------------------------------------------------------------------------
# Internal-$ref dereferencing for the embedded Swagger UI page
# ---------------------------------------------------------------------------

_MISSING: Any = object()


def _split_pointer(pointer: str) -> list[str]:
    """Splits a JSON Pointer into decoded segments, per RFC 6901.

    "" -> []; "/" -> [""]; "/a/b" -> ["a", "b"]; "//" -> ["", ""].
    Only "~1" ("/") and "~0" ("~") escapes are decoded, in that order.
    """
    if pointer == "":
        return []
    return [
        segment.replace("~1", "/").replace("~0", "~")
        for segment in pointer[1:].split("/")
    ]


def _lookup_pointer(document: Any, pointer: str) -> Any:
    """Navigates *document* by a JSON Pointer; returns _MISSING if absent.

    A valid pointer is either empty (the whole document) or starts with
    "/" (RFC 6901); anything else is malformed and treated as unresolvable
    rather than raised, keeping the renderer best-effort.
    """
    if pointer and not pointer.startswith("/"):
        return _MISSING
    current: Any = document
    for segment in _split_pointer(pointer):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        elif (
            isinstance(current, list)
            and segment.isdigit()
            and int(segment) < len(current)
        ):
            current = current[int(segment)]
        else:
            return _MISSING
    return current


def _recursive_stub(ref: str) -> dict:
    """Placeholder emitted instead of re-entering a cyclic reference."""
    return {
        "type": "object",
        "description": (
            f"Recursive reference {ref} is collapsed here to keep the "
            "embedded specification finite; the full definition is "
            "available in the Schemas section."
        ),
    }


def _unresolved_stub(ref: str) -> dict:
    """Placeholder emitted for a dangling or malformed reference."""
    return {"description": f"Unresolved reference: {ref}"}


def _dereference(node: Any, active: tuple[str, ...], root: Any) -> Any:
    """Rebuilds *node* with every internal ``$ref`` replaced by its target.

    The function is pure: it never mutates its input, and the returned tree
    never aliases *root* or *node*.

    ``active`` is the stack of pointers currently being expanded; a ref whose
    pointer is already on the stack is a cycle and collapses into a stub.
    External refs (values not starting with ``#``) are kept as-is.
    """
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#"):
            pointer: str = ref[1:]
            siblings: dict = {
                key: _dereference(value, active, root)
                for key, value in node.items()
                if key != "$ref"
            }
            if pointer in active:
                stub = _recursive_stub(ref)
                stub.update(siblings)
                return stub
            target: Any = _lookup_pointer(root, pointer)
            if target is _MISSING:
                stub = _unresolved_stub(ref)
                stub.update(siblings)
                return stub
            expanded: Any = _dereference(target, active + (pointer,), root)
            if isinstance(expanded, dict):
                # OpenAPI 3.1 allows $ref siblings; siblings win.
                expanded.update(siblings)
            elif siblings:
                _logger.warning(
                    "dereference_internal_refs: $ref %r resolved to a "
                    "non-object node; its siblings %r were dropped",
                    ref,
                    sorted(siblings),
                )
            return expanded
        return {key: _dereference(value, active, root) for key, value in node.items()}
    if isinstance(node, list):
        return [_dereference(item, active, root) for item in node]
    return node


def dereference_internal_refs(spec: dict) -> dict:
    """Returns a rebuilt copy of *spec* with all internal ``$ref`` inlined.

    Why: Swagger UI resolves ``$ref`` pointers at runtime. Even when the
    document is embedded through the ``spec`` option, expanding an endpoint
    makes the resolver build an absolute URI for each reference from the
    page address (``file:///...swagger.html#/components/...``) and ask the
    browser to fetch that document. Browsers block fetch/XHR against
    ``file://``, so opening the page from disk fails with
    ``Evaluation failed on URI``. A document without a single ``$ref`` gives
    the resolver nothing to fetch, which makes the HTML artifact work
    offline from a double-click.

    Notes:
        * The input document is not modified.
        * External references are preserved untouched.
        * Recursive schemas collapse into a described stub object, so cycles
          cannot cause infinite recursion.
        * Schemas are duplicated at each usage site: operations show
          expanded models instead of links to the Schemas section.
        * Stub placeholders keep their diagnostic in ``description``; a
          sibling that also defines ``description`` replaces the diagnostic
          (sibling-wins semantics, as everywhere else).
    """
    result: Any = _dereference(spec, (), spec)
    if not isinstance(result, dict):
        raise TypeError("dereference_internal_refs requires a dict root")
    return result


class OpenApiRenderer:
    """Converts domain ApiDesign model to OpenAPI 3.1.0 specification dictionary."""

    def render_spec(self, api: ApiDesign) -> dict:
        paths: dict[str, dict] = {}

        for op in api.operations:
            if op.path not in paths:
                paths[op.path] = {}

            op_spec: dict = {
                "operationId": op.operation_id,
                "summary": op.summary,
                "x-entrypoint-component": op.entrypoint_component_id,
                "x-handler-component": op.handler_component_id,
                "x-requirement-ids": op.requirement_ids,
                "x-sequence-ids": op.sequence_ids,
            }
            if op.description:
                op_spec["description"] = op.description

            if op.security_required:
                op_spec["security"] = [{"bearerAuth": []}]

            # Parameters
            if op.parameters:
                op_spec["parameters"] = [
                    self._render_parameter(p) for p in op.parameters
                ]

            # Request Body
            if op.request_body:
                op_spec["requestBody"] = {
                    "required": op.request_body.required,
                    "content": {
                        op.request_body.content_type: {
                            "schema": {
                                "$ref": f"#/components/schemas/{op.request_body.schema_ref}"
                            }
                        }
                    },
                }

            # Responses
            responses_spec: dict[str, dict] = {}
            for resp in op.responses:
                resp_data: dict = {"description": resp.description}
                if resp.schema_ref and resp.content_type:
                    resp_data["content"] = {
                        resp.content_type: {
                            "schema": {
                                "$ref": f"#/components/schemas/{resp.schema_ref}"
                            }
                        }
                    }
                responses_spec[resp.status_code] = resp_data
            op_spec["responses"] = responses_spec

            paths[op.path][op.method.value] = op_spec

        # Components
        components: dict[str, dict] = {"schemas": api.schemas}
        components["securitySchemes"] = {
            "bearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
            }
        }

        return {
            "openapi": "3.1.0",
            "info": {
                "title": api.title,
                "version": api.version,
                "description": api.description or "Generated by AutoSystemDesign",
            },
            "paths": paths,
            "components": components,
        }

    @staticmethod
    def _render_parameter(param: ApiParameter) -> dict:
        schema: dict = {"type": param.data_type.value}
        if param.format:
            schema["format"] = param.format
        if param.data_type == DataType.ARRAY and param.item_type:
            schema["items"] = {"type": param.item_type.value}

        result: dict = {
            "name": param.name,
            "in": param.in_location.value,
            "required": param.required,
            "schema": schema,
        }
        if param.description:
            result["description"] = param.description
        return result


class SwaggerUiRenderer:
    """Builds a single-file HTML viewer embedding OpenAPI spec with CDN assets.

    The specification is embedded through the ``spec`` option (never
    ``url:``) and fully dereferenced first, so the page performs no request
    for the specification and contains no references left for the runtime
    resolver to fetch. Only the Swagger UI assets themselves (CSS/JS from
    unpkg.com) require an internet connection; if they cannot be loaded,
    the page shows an explanatory message instead of a blank screen.

    The Standalone preset (top bar with the Authorize button and Try-it-out
    controls) is loaded from its own script -- in swagger-ui-dist 5.x it is
    NOT exposed as ``SwaggerUIBundle.SwaggerUIStandalonePreset`` -- and is
    wired up defensively: if that script fails to load, the page falls back
    to the base layout instead of pushing ``undefined`` into the presets
    array.
    """

    def render_html(self, spec_dict: dict, title: str) -> str:
        embedded_spec: dict = dereference_internal_refs(spec_dict)
        safe_spec: str = safe_json_for_script(embedded_spec)
        escaped_title: str = html.escape(title)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escaped_title} - Swagger UI</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
  <style>
    body {{ margin: 0; padding: 0; background-color: #fafafa; }}
    #swagger-ui {{ max-width: 1280px; margin: 0 auto; }}
  </style>
  <!--
    The OpenAPI document below is embedded through the `spec` option with
    every internal $ref already inlined. Do not switch this to `url:`:
    pages opened from the file system cannot fetch sibling files, and the
    $ref resolver cannot fetch file:// URIs either.
  -->
</head>
<body>
<div id="swagger-ui"></div>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js" charset="UTF-8"></script>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-standalone-preset.js" charset="UTF-8"></script>
<script>
  window.onload = () => {{
    if (typeof SwaggerUIBundle === "undefined") {{
      document.getElementById("swagger-ui").innerHTML =
        '<div style="font: 16px sans-serif; padding: 24px;">'
        + '<strong>Swagger UI failed to load.</strong> '
        + 'The viewer assets are fetched from unpkg.com and need internet '
        + 'access. The embedded specification itself is complete.';
      return;
    }}
    const spec = {safe_spec};
    const presets = [SwaggerUIBundle.presets.apis];
    const hasStandalone = typeof SwaggerUIStandalonePreset !== "undefined";
    if (hasStandalone) {{
      presets.push(SwaggerUIStandalonePreset);
    }}
    window.ui = SwaggerUIBundle({{
      spec: spec,
      dom_id: '#swagger-ui',
      deepLinking: true,
      presets: presets,
      layout: hasStandalone ? "StandaloneLayout" : "BaseLayout",
    }});
  }};
</script>
</body>
</html>
"""
