# Copyright (c) 2026 Volodya1000
"""Message-broker linkage: every broker must bridge two DIFFERENT compute nodes.

A ``MessageBrokerNode`` is a routing element. Three distinct defects are
possible, and each is reported separately so the repair prompt names the
exact fix:

* broker with incoming but no outgoing edges -- a routing *dead-end*;
* broker with outgoing but no incoming edges -- a *phantom source*;
* broker whose producer and consumer are the same compute node -- a
  *self-loop*: ``A -> broker -> A`` is a cycle, and the only valid fix is
  to add a dedicated worker compute node behind the broker.

The fully disconnected broker (no edges at all) is reported by
``IsolatedNodeError`` in ``structural_rules.py`` and is *not* repeated
here.

Pure module: no I/O, no logging, no clock. Set-based, so cycles are
irrelevant to this rule -- cycle detection belongs to
``StructuralTopologyValidator``, which runs in the same aggregation pass.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from domain.exceptions.architecture_errors import (
    ArchitectureValidationError,
    MessageBrokerSelfLoopError,
    MessageBrokerWithoutConsumerError,
    MessageBrokerWithoutProducerError,
)
from domain.models.nodes import MessageBrokerNode
from domain.specifications.interfaces import BaseValidator, ValidationResult

if TYPE_CHECKING:
    from domain.models.topology import ArchitectureGraph


def check_message_broker_linkage(
    graph: ArchitectureGraph,
) -> list[ArchitectureValidationError]:
    """Return one error per broker with a broken producer/consumer link.

    Errors are mutually exclusive per broker: the check walks the states in
    order (no producer, no consumer, self-loop) and stops at the first
    defect. This keeps the repair prompt focused on one actionable fix per
    broker, even when several brokers are broken at once.
    """
    incoming: dict[str, list[str]] = {}
    outgoing: dict[str, list[str]] = {}
    for edge in graph.edges:
        outgoing.setdefault(edge.source_identifier, []).append(edge.target_identifier)
        incoming.setdefault(edge.target_identifier, []).append(edge.source_identifier)

    errors: list[ArchitectureValidationError] = []
    for node in graph.nodes:
        if not isinstance(node, MessageBrokerNode):
            continue

        producers = set(incoming.get(node.identifier, ()))
        consumers = set(outgoing.get(node.identifier, ()))

        if not producers and not consumers:
            # Fully isolated: StructuralTopologyValidator reports it.
            continue
        if not producers:
            errors.append(MessageBrokerWithoutProducerError(node.identifier))
            continue
        if not consumers:
            errors.append(MessageBrokerWithoutConsumerError(node.identifier))
            continue

        shared = producers & consumers
        if shared:
            errors.append(
                MessageBrokerSelfLoopError(
                    broker_identifier=node.identifier,
                    compute_identifiers=sorted(shared),
                )
            )

    return errors


class MessageBrokerConsumerValidator(BaseValidator):
    """Flags brokers missing a producer, a consumer, or using one node for both."""

    @override
    def validate(self, graph: ArchitectureGraph) -> ValidationResult:
        return ValidationResult(errors=check_message_broker_linkage(graph))
