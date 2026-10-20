"""Internal-$ref dereferencing for the embedded Swagger UI page.

This module only handles JSON-Pointer resolution: it rebuilds a document
with every internal ``$ref`` replaced by its target, making the result
self-contained for offline viewing. Kept apart from OpenAPI specification
rendering and Swagger HTML generation so the logic can evolve and be
tested independently.
"""

from __future__ import annotations

import logging
from typing import Any

_logger: logging.Logger = logging.getLogger(__name__)

_MISSING: Any = object()


class InvalidDereferenceRootError(TypeError):
    """Raised when dereferencing does not produce a mapping root."""

    def __init__(self) -> None:
        super().__init__("dereference_internal_refs requires a dict root")


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


def _lookup_pointer(document: object, pointer: str) -> object:
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


def _dereference(node: object, active: tuple[str, ...], root: object) -> object:
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
            expanded: Any = _dereference(target, (*active, pointer), root)
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
        raise InvalidDereferenceRootError
    return result
