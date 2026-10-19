"""Unit tests of MessageBrokerConsumerValidator.

The validator catches brokers that receive messages but route them nowhere.
The tests cover the happy path, the exact failure mode, the "not my job"
cases (broker with no edges / broker with wrong outgoing edge type), and
multi-broker graphs.
"""

from __future__ import annotations

import pytest

from domain.exceptions.architecture_errors import (
    MessageBrokerSelfLoopError,
    MessageBrokerWithoutConsumerError,
    MessageBrokerWithoutProducerError,
)
from domain.models.enums import NodeType
from domain.models.nodes import ComputeNode, MessageBrokerNode
from domain.models.topology import AnyNode, ArchitectureGraph
from domain.specifications.broker_consumer_validator import (
    MessageBrokerConsumerValidator,
)
from domain.specifications.structural_validator import StructuralTopologyValidator
from tests.unit.test_structural_validator import (
    create_test_edge,
    create_test_node,
)

pytestmark = pytest.mark.unit


# ------------------------------------------------------------------ helpers


def _broker(identifier: str) -> MessageBrokerNode:
    return MessageBrokerNode(
        identifier=identifier,
        maximum_concurrency=500,
        maximum_queue_size=100_000,
        mean_processing_time_milliseconds=3.0,
        standard_deviation_processing_time=1.0,
        monthly_cost_usd=60.0,
    )


def _consumer(identifier: str) -> ComputeNode:
    return ComputeNode(
        identifier=identifier,
        maximum_concurrency=200,
        maximum_queue_size=1_000,
        mean_processing_time_milliseconds=10.0,
        standard_deviation_processing_time=2.0,
        monthly_cost_usd=80.0,
    )


def _graph(*nodes: AnyNode, edges_pairs: list[tuple[str, str]]) -> ArchitectureGraph:
    return ArchitectureGraph(
        nodes=list(nodes),
        edges=[create_test_edge(src, dst) for src, dst in edges_pairs],
    )


# ------------------------------------------------------------ happy path


class TestBrokerWithConsumer:
    def test_broker_with_outgoing_edge_is_accepted(self) -> None:
        """The canonical pattern: producer -> broker -> consumer."""
        graph = _graph(
            create_test_node("client", NodeType.CLIENT),
            create_test_node("producer", NodeType.COMPUTE),
            _broker("broker_1"),
            _consumer("worker_1"),
            edges_pairs=[
                ("client", "producer"),
                ("producer", "broker_1"),
                ("broker_1", "worker_1"),
            ],
        )

        result = MessageBrokerConsumerValidator().validate(graph)

        assert result.is_successful is True
        assert result.errors == []

    def test_no_brokers_in_graph_is_accepted(self) -> None:
        graph = _graph(
            create_test_node("client", NodeType.CLIENT),
            create_test_node("compute", NodeType.COMPUTE),
            edges_pairs=[("client", "compute")],
        )

        result = MessageBrokerConsumerValidator().validate(graph)

        assert result.is_successful is True


# -------------------------------------------------------- failure mode


class TestDanglingBroker:
    def test_broker_with_incoming_but_no_outgoing_is_rejected(self) -> None:
        """Reproduce the exact pattern the LLM produced on the

        social_network_chat run: processor -> broker (async), but the
        broker has no consumer. Messages accumulate in the queue forever."""
        graph = _graph(
            create_test_node("client", NodeType.CLIENT),
            create_test_node("processor", NodeType.COMPUTE),
            _broker("message_broker"),
            edges_pairs=[
                ("client", "processor"),
                ("processor", "message_broker"),
            ],
        )

        result = MessageBrokerConsumerValidator().validate(graph)

        assert result.is_successful is False
        errors = [
            e for e in result.errors if isinstance(e, MessageBrokerWithoutConsumerError)
        ]
        assert len(errors) == 1
        assert errors[0].affected_node_identifiers == ["message_broker"]
        # The message must be actionable for the repair prompt: identify
        # the node and point at the fix.
        message = errors[0].message
        assert "message_broker" in message
        assert "consumer" in message
        assert "compute" in message

    def test_multiple_dangling_brokers_each_get_their_own_error(self) -> None:
        graph = _graph(
            create_test_node("client", NodeType.CLIENT),
            create_test_node("processor", NodeType.COMPUTE),
            _broker("broker_a"),
            _broker("broker_b"),
            edges_pairs=[
                ("client", "processor"),
                ("processor", "broker_a"),
                ("processor", "broker_b"),
            ],
        )

        result = MessageBrokerConsumerValidator().validate(graph)

        identifiers = sorted(
            e.affected_node_identifiers[0]
            for e in result.errors
            if isinstance(e, MessageBrokerWithoutConsumerError)
        )
        assert identifiers == ["broker_a", "broker_b"]


# ----------------------------------------------------------- "not my job"


class TestScopeBoundaries:
    def test_isolated_broker_is_structural_not_ours(self) -> None:
        """Avoid double-reporting a broker with neither incoming nor outgoing edges.

        Such a broker is handled by IsolatedNodeError (empty incoming means no fire).
        """
        graph = _graph(
            create_test_node("client", NodeType.CLIENT),
            create_test_node("compute", NodeType.COMPUTE),
            _broker("orphan_broker"),
            edges_pairs=[("client", "compute")],
        )

        our_result = MessageBrokerConsumerValidator().validate(graph)
        structural_result = StructuralTopologyValidator().validate(graph)

        assert our_result.is_successful is True
        # Sanity: the structural validator is responsible for the case.
        assert structural_result.is_successful is False

    def test_broker_with_only_outgoing_edges_is_flagged_as_phantom_source(self) -> None:
        """A broker with outgoing edges but no incoming edge is a phantom

        source: consumers receive messages that no one published. It must
        be reported as MessageBrokerWithoutProducerError, not accepted.

        The counterpart of ``TestDanglingBroker`` (incoming but no
        outgoing). Both ends of the bridge are required, and both defects
        are checked.
        """
        graph = _graph(
            _broker("orphan_broker"),
            _consumer("worker_1"),
            edges_pairs=[("orphan_broker", "worker_1")],
        )

        result = MessageBrokerConsumerValidator().validate(graph)

        assert result.is_successful is False
        producer_errors = [
            e for e in result.errors if isinstance(e, MessageBrokerWithoutProducerError)
        ]
        assert len(producer_errors) == 1
        assert producer_errors[0].affected_node_identifiers == ["orphan_broker"]

    def test_broker_with_disallowed_outgoing_edge_is_not_flagged_here(self) -> None:
        """Broker -> non-consumer edge is a connection-whitelist error

        (DisallowedConnectionTypeError), not ours. The broker DOES have an
        outgoing edge, so we do not fire."""
        graph = _graph(
            create_test_node("client", NodeType.CLIENT),
            create_test_node("processor", NodeType.COMPUTE),
            _broker("broker_1"),
            create_test_node("db_1", NodeType.DATABASE),
            edges_pairs=[
                ("client", "processor"),
                ("processor", "broker_1"),
                ("broker_1", "db_1"),  # broker -> database: disallowed
            ],
        )

        our_result = MessageBrokerConsumerValidator().validate(graph)

        assert our_result.is_successful is True


# ----------------------------------------------------- cycle-tolerance


class TestCycleTolerance:
    def test_cyclic_graph_does_not_crash(self) -> None:
        """The rule is set-based, so cycles are irrelevant to it.

        Cycle reporting is owned by StructuralTopologyValidator; this
        validator must simply return without raising when a cycle is
        present, otherwise the repair loop would abort before F1's error
        reaches the model.
        """
        graph = _graph(
            create_test_node("compute_1", NodeType.COMPUTE),
            create_test_node("compute_2", NodeType.COMPUTE),
            edges_pairs=[
                ("compute_1", "compute_2"),
                ("compute_2", "compute_1"),
            ],
        )

        result = MessageBrokerConsumerValidator().validate(graph)

        assert result.is_successful is True
        assert result.errors == []


class TestPhantomSourceBroker:
    def test_broker_with_outgoing_but_no_incoming_is_rejected(self) -> None:
        """The regression the second live run exposed: the model removed

        the producer edge and added a consumer edge, so the broker became
        a source of messages that no one published.
        """
        graph = _graph(
            create_test_node("client", NodeType.CLIENT),
            create_test_node("processor", NodeType.COMPUTE),
            _broker("message_broker"),
            edges_pairs=[
                ("client", "processor"),
                ("message_broker", "processor"),  # consumer, but no producer
            ],
        )

        result = MessageBrokerConsumerValidator().validate(graph)

        assert result.is_successful is False
        errors = [
            e for e in result.errors if isinstance(e, MessageBrokerWithoutProducerError)
        ]
        assert len(errors) == 1
        assert errors[0].affected_node_identifiers == ["message_broker"]
        message = errors[0].message
        assert "message_broker" in message
        assert "producer" in message
        assert "compute" in message

    def test_phantom_source_does_not_also_report_missing_consumer(self) -> None:
        """Keep the error directional.

        A missing producer must not also be reported as a missing consumer.
        """
        graph = _graph(
            create_test_node("client", NodeType.CLIENT),
            create_test_node("processor", NodeType.COMPUTE),
            _broker("message_broker"),
            edges_pairs=[
                ("client", "processor"),
                ("message_broker", "processor"),
            ],
        )

        result = MessageBrokerConsumerValidator().validate(graph)

        assert not any(
            isinstance(e, MessageBrokerWithoutConsumerError) for e in result.errors
        )


class TestFullyIsolatedBroker:
    def test_isolated_broker_is_not_double_reported(self) -> None:
        """Fully isolated brokers belong to StructuralTopologyValidator

        (IsolatedNodeError). The linkage validator must skip them so the
        repair prompt is not crowded with duplicate diagnostics for one
        defect."""
        graph = _graph(
            create_test_node("client", NodeType.CLIENT),
            create_test_node("compute", NodeType.COMPUTE),
            _broker("orphan_broker"),  # no edges at all
            edges_pairs=[("client", "compute")],
        )

        result = MessageBrokerConsumerValidator().validate(graph)

        assert result.is_successful is True
        assert result.errors == []


class TestSelfLoopBroker:
    def test_same_node_as_producer_and_consumer_is_rejected(self) -> None:
        """The exact pattern the third live run produced:

        processor -> broker -> processor. Structurally this is a cycle
        (caught by StructuralTopologyValidator), but a broker-specific
        error gives the model an actionable fix instead of a generic
        cycle message.
        """
        graph = _graph(
            create_test_node("client", NodeType.CLIENT),
            create_test_node("processor", NodeType.COMPUTE),
            _broker("message_broker"),
            edges_pairs=[
                ("client", "processor"),
                ("processor", "message_broker"),
                ("message_broker", "processor"),
            ],
        )

        result = MessageBrokerConsumerValidator().validate(graph)

        assert result.is_successful is False
        self_loop_errors = [
            e for e in result.errors if isinstance(e, MessageBrokerSelfLoopError)
        ]
        assert len(self_loop_errors) == 1
        error = self_loop_errors[0]
        assert error.affected_node_identifiers == ["message_broker", "processor"]
        message = error.message
        assert "'message_broker'" in message
        assert "'processor'" in message
        assert "DIFFERENT" in message
        assert "worker" in message.lower()

    def test_different_producer_and_consumer_accepted(self) -> None:
        """Canonical pattern: producer -> broker -> worker (distinct nodes)."""
        graph = _graph(
            create_test_node("client", NodeType.CLIENT),
            create_test_node("producer", NodeType.COMPUTE),
            _broker("broker_1"),
            _consumer("worker_1"),
            edges_pairs=[
                ("client", "producer"),
                ("producer", "broker_1"),
                ("broker_1", "worker_1"),
            ],
        )

        result = MessageBrokerConsumerValidator().validate(graph)

        assert result.is_successful is True

    def test_self_loop_does_not_also_report_missing_ends(self) -> None:
        """One error per broker: the self-loop check subsumes both ends."""
        graph = _graph(
            create_test_node("client", NodeType.CLIENT),
            create_test_node("processor", NodeType.COMPUTE),
            _broker("message_broker"),
            edges_pairs=[
                ("client", "processor"),
                ("processor", "message_broker"),
                ("message_broker", "processor"),
            ],
        )

        result = MessageBrokerConsumerValidator().validate(graph)

        assert not any(
            isinstance(e, MessageBrokerWithoutProducerError) for e in result.errors
        )
        assert not any(
            isinstance(e, MessageBrokerWithoutConsumerError) for e in result.errors
        )
