"""Formatting of pydantic error locations as JSONPath-like strings.

Shared by every parser in this package (architecture graph, API design,
sequence scenarios). The leading underscore on the module name marks it
as package-internal; the function itself has no underscore prefix so the
three parsers can import it as siblings without reaching into a private
symbol defined by one of them.
"""

from __future__ import annotations


def format_error_location(loc: tuple[int | str, ...]) -> str:
    """Formats a pydantic error location as a JSONPath-like string."""
    if not loc:
        return "$"
    path: str = str(loc[0])
    for part in loc[1:]:
        if isinstance(part, int):
            path = f"{path}[{part}]"
        else:
            path = f"{path}.{part}"
    return f"$.{path}"
