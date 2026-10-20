"""Cache read/write linkage: a cache must be read from, and misses must land.

Two distinct defects are possible for a cache node:

* a **write-only sink**: every incoming edge is asynchronous, meaning the
  cache only ever receives fire-and-forget writes and nobody reads from
  it, so ``cache_hit_rate_probability`` is dead configuration;
* a **broken miss path**: the cache is read synchronously by a compute
  node whose only outgoing edge goes to that cache, so a cache miss has
  nowhere to fall back to (the caller cannot resolve the miss).

A fully disconnected cache (no edges at all) is reported by
``IsolatedNodeError`` in ``structural_rules.py`` and is not repeated here.

Design note on "miss path": ``DEFAULT_ALLOWED_CONNECTION_TYPES`` forbids
edges *from* a cache, so the miss path is modelled as a **fallback edge
of the compute node that reads from the cache** (typically
``compute -> database``). The validator checks that fallback exists.

Pure module: no I/O, no logging, no clock. Set-based, so cycles are
irrelevant to this rule -- cycle detection belongs to
``StructuralTopologyValidator``, which runs in the same aggregation pass.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.exceptions.architecture_errors import (
    ArchitectureValidationError,
    CacheMissPathMissingError,
    CacheWriteOnlySinkError,
)
from domain.models.nodes import CacheNode
from domain.specifications.interfaces import BaseValidator, ValidationResult

if TYPE_CHECKING:
    from domain.models.edges import Edge
    from domain.models.topology import ArchitectureGraph


def check_cache_usage(
    graph: ArchitectureGraph,
) -> list[ArchitectureValidationError]:
    """Return one error per cache with a write-only or miss-path defect.

    The two checks are mutually exclusive per cache: a write-only sink has
    no synchronous readers, so the miss-path check has nothing to verify.
    """
    incoming: dict[str, list[Edge]] = {}
    outgoing: dict[str, list[Edge]] = {}
    for edge in graph.edges:
        incoming.setdefault(edge.target_identifier, []).append(edge)
        outgoing.setdefault(edge.source_identifier, []).append(edge)

    errors: list[ArchitectureValidationError] = []
    for node in graph.nodes:
        if not isinstance(node, CacheNode):
            continue

        cache_incoming = incoming.get(node.identifier, [])
        if not cache_incoming:
            # Fully isolated: StructuralTopologyValidator reports it as
            # IsolatedNodeError; do not double-report.
            continue

        sync_incoming = [
            edge for edge in cache_incoming if not edge.protocol.is_asynchronous
        ]

        if not sync_incoming:
            source_ids = sorted({edge.source_identifier for edge in cache_incoming})
            errors.append(
                CacheWriteOnlySinkError(
                    cache_identifier=node.identifier,
                    incoming_source_identifiers=source_ids,
                )
            )
            continue

        for source_id in sorted({edge.source_identifier for edge in sync_incoming}):
            source_outgoing = outgoing.get(source_id, [])
            non_cache_fallbacks = [
                edge
                for edge in source_outgoing
                if edge.target_identifier != node.identifier
            ]
            if not non_cache_fallbacks:
                errors.append(
                    CacheMissPathMissingError(
                        cache_identifier=node.identifier,
                        compute_identifier=source_id,
                    )
                )

    return errors


class CacheUsageValidator(BaseValidator):
    """Flags write-only caches and caches whose miss path is broken."""

    def validate(self, graph: ArchitectureGraph) -> ValidationResult:
        return ValidationResult(errors=check_cache_usage(graph))
