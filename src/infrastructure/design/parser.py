"""Architecture-graph parser.

``extract_json_payload`` is re-exported here for backward compatibility:
it used to live in this module and is used directly by some tests and
external callers. New code should import it from
``infrastructure.design._parsing`` alongside ``parse_payload``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.models.topology import ArchitectureGraph
from infrastructure.design._parsing import extract_json_payload, parse_payload

if TYPE_CHECKING:
    from application.usage import TokenUsage

__all__ = ["extract_json_payload", "parse_architecture_graph"]


def parse_architecture_graph(payload: str, usage: TokenUsage) -> ArchitectureGraph:
    """Parses a raw LLM completion into an ArchitectureGraph."""
    return parse_payload(payload, ArchitectureGraph, usage)
