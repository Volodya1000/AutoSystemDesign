"""Validate cache read paths and each reader's database fallback.

A cache read is represented by two edges from the same compute node:
compute -> cache for the lookup and compute -> database for the miss fallback.
The cache does not call the database itself. Every synchronous reader must have
a synchronous database fallback; a compute node reading multiple caches is
rejected because this graph contract cannot identify which cache a fallback
belongs to.

Pure module: no I/O, no logging, no clock. Cycle detection belongs to
StructuralTopologyValidator, which runs in the same validation pass.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.exceptions.architecture_errors import (
    AmbiguousCacheMissPathError,
    ArchitectureValidationError,
    CacheMissPathMissingError,
    CacheWriteOnlySinkError,
)
from domain.models.nodes import CacheNode, DatabaseNode
from domain.specifications.interfaces import BaseValidator, ValidationResult

if TYPE_CHECKING:
    from domain.models.edges import Edge
    from domain.models.topology import AnyNode, ArchitectureGraph


def _index_edges(
    graph: ArchitectureGraph,
) -> tuple[dict[str, list[Edge]], dict[str, list[Edge]]]:
    incoming: dict[str, list[Edge]] = {}
    outgoing: dict[str, list[Edge]] = {}
    for edge in graph.edges:
        incoming.setdefault(edge.target_identifier, []).append(edge)
        outgoing.setdefault(edge.source_identifier, []).append(edge)
    return incoming, outgoing


def _find_ambiguous_readers(
    graph: ArchitectureGraph,
    incoming: dict[str, list[Edge]],
) -> dict[str, list[str]]:
    cache_targets_by_reader: dict[str, set[str]] = {}
    for node in graph.nodes:
        if not isinstance(node, CacheNode):
            continue
        for edge in incoming.get(node.identifier, []):
            if edge.protocol.is_asynchronous:
                continue
            cache_targets_by_reader.setdefault(edge.source_identifier, set()).add(
                node.identifier
            )

    return {
        source_id: sorted(cache_ids)
        for source_id, cache_ids in cache_targets_by_reader.items()
        if len(cache_ids) > 1
    }


def _has_database_fallback(
    source_id: str,
    outgoing: dict[str, list[Edge]],
    node_by_id: dict[str, AnyNode],
) -> bool:
    return any(
        not edge.protocol.is_asynchronous
        and isinstance(node_by_id.get(edge.target_identifier), DatabaseNode)
        for edge in outgoing.get(source_id, [])
    )


def _cache_read_errors(
    cache: CacheNode,
    incoming: dict[str, list[Edge]],
    outgoing: dict[str, list[Edge]],
    node_by_id: dict[str, AnyNode],
    ambiguous_readers: dict[str, list[str]],
) -> list[ArchitectureValidationError]:
    cache_incoming = incoming.get(cache.identifier, [])
    if not cache_incoming:
        # Isolated nodes and forbidden cache outgoing edges belong to the
        # structural validator.
        return []

    sync_incoming = [
        edge for edge in cache_incoming if not edge.protocol.is_asynchronous
    ]
    if not sync_incoming:
        source_ids = sorted({edge.source_identifier for edge in cache_incoming})
        return [
            CacheWriteOnlySinkError(
                cache_identifier=cache.identifier,
                incoming_source_identifiers=source_ids,
            )
        ]

    errors: list[ArchitectureValidationError] = []
    reader_ids = sorted({edge.source_identifier for edge in sync_incoming})
    for source_id in reader_ids:
        if source_id in ambiguous_readers:
            continue
        if _has_database_fallback(source_id, outgoing, node_by_id):
            continue
        errors.append(
            CacheMissPathMissingError(
                cache_identifier=cache.identifier,
                compute_identifier=source_id,
            )
        )
    return errors


def check_cache_usage(
    graph: ArchitectureGraph,
) -> list[ArchitectureValidationError]:
    """Return errors for unread caches, missing miss paths, or ambiguous readers."""
    incoming, outgoing = _index_edges(graph)
    node_by_id = {node.identifier: node for node in graph.nodes}
    ambiguous_readers = _find_ambiguous_readers(graph, incoming)
    errors: list[ArchitectureValidationError] = [
        AmbiguousCacheMissPathError(source_id, cache_ids)
        for source_id, cache_ids in sorted(ambiguous_readers.items())
    ]

    for node in graph.nodes:
        if isinstance(node, CacheNode):
            errors.extend(
                _cache_read_errors(
                    node,
                    incoming,
                    outgoing,
                    node_by_id,
                    ambiguous_readers,
                )
            )
    return errors


class CacheUsageValidator(BaseValidator):
    """Flags write-only caches and caches whose miss path is broken."""

    def validate(self, graph: ArchitectureGraph) -> ValidationResult:
        return ValidationResult(errors=check_cache_usage(graph))
