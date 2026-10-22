"""Map C4 topology into typed simulation inputs without invoking an LLM."""

from enum import StrEnum
from heapq import heappop, heappush

from domain.architecture_simulation.graph_plan import (
    GraphSimulationPlan,
    SimulatedConnection,
    SimulatedResource,
)
from domain.models.edges import Edge
from domain.models.nodes import (
    CacheNode,
    CapacityNode,
    ClientNode,
    MessageBrokerNode,
)
from domain.models.scenarios import DesignScenario
from domain.models.topology import AnyNode, ArchitectureGraph


class MappingFailure(StrEnum):
    """Categorize unsupported or inconsistent input without fragile messages."""

    MISSING_WORKLOAD = "missing_workload"
    INVALID_CLIENT_COUNT = "invalid_client_count"
    DUPLICATE_NODE = "duplicate_node"
    UNKNOWN_ENDPOINT = "unknown_endpoint"
    DUPLICATE_EDGE = "duplicate_edge"
    UNSUPPORTED_ASYNC = "unsupported_async"
    UNSUPPORTED_RETRY = "unsupported_retry"
    UNSUPPORTED_BROKER = "unsupported_broker"
    SERVICE_CHANNELS_UNKNOWN = "service_channels_unknown"
    CYCLE = "cycle"
    DISCONNECTED = "disconnected"


class GraphMappingError(ValueError):
    """Preserve a typed reason for non-modelled graph semantics."""

    def __init__(self, code: MappingFailure, identifier: str) -> None:
        self.code: MappingFailure = code
        self.identifier: str = identifier
        super().__init__(f"{code.value}: {identifier}")


class ArchitectureSimulationPlanMapper:
    """Produce a deterministic, strictly supported simulation graph."""

    def map(
        self, graph: ArchitectureGraph, scenario: DesignScenario
    ) -> GraphSimulationPlan:
        """Validate topology before converting timings from milliseconds."""
        workload = scenario.workload
        if workload is None:
            raise GraphMappingError(MappingFailure.MISSING_WORKLOAD, scenario.identifier)

        nodes: dict[str, AnyNode] = {}
        node: AnyNode
        for node in graph.nodes:
            if node.identifier in nodes:
                raise GraphMappingError(MappingFailure.DUPLICATE_NODE, node.identifier)
            nodes[node.identifier] = node

        clients: list[str] = sorted(
            identifier
            for identifier, member in nodes.items()
            if isinstance(member, ClientNode)
        )
        if len(clients) != 1:
            raise GraphMappingError(
                MappingFailure.INVALID_CLIENT_COUNT, str(len(clients))
            )
        client_identifier: str = clients[0]
        edges: list[Edge] = sorted(
            graph.edges,
            key=lambda edge: (
                edge.source_identifier,
                edge.target_identifier,
                edge.routing_mode,
            ),
        )
        self._validate_edges(edges, nodes)
        order: list[str] = self._ordered_nodes(nodes, edges, client_identifier)
        resources: list[SimulatedResource] = [
            self._map_resource(member)
            for identifier, member in sorted(nodes.items())
            if identifier != client_identifier
        ]
        connections: list[SimulatedConnection] = [
            SimulatedConnection(
                source_identifier=edge.source_identifier,
                target_identifier=edge.target_identifier,
                routing_mode=edge.routing_mode,
                network_latency_seconds=edge.network_latency_milliseconds / 1000.0,
                timeout_seconds=edge.timeout_milliseconds / 1000.0,
            )
            for edge in edges
        ]
        return GraphSimulationPlan(
            scenario_identifier=scenario.identifier,
            client_identifier=client_identifier,
            baseline_requests_per_second=workload.baseline_requests_per_second,
            peak_requests_per_second=workload.peak_requests_per_second,
            resources=resources,
            connections=connections,
            topological_order=order,
        )

    def _validate_edges(self, edges: list[Edge], nodes: dict[str, AnyNode]) -> None:
        """Reject invalid references and semantics not simulated in V1."""
        seen: set[tuple[str, str]] = set()
        edge: Edge
        for edge in edges:
            key: tuple[str, str] = (
                edge.source_identifier,
                edge.target_identifier,
            )
            if edge.source_identifier not in nodes:
                raise GraphMappingError(
                    MappingFailure.UNKNOWN_ENDPOINT, edge.source_identifier
                )
            if edge.target_identifier not in nodes:
                raise GraphMappingError(
                    MappingFailure.UNKNOWN_ENDPOINT, edge.target_identifier
                )
            if key in seen:
                raise GraphMappingError(
                    MappingFailure.DUPLICATE_EDGE, edge.source_identifier
                )
            seen.add(key)
            if edge.protocol.is_asynchronous:
                raise GraphMappingError(
                    MappingFailure.UNSUPPORTED_ASYNC, edge.target_identifier
                )
            if edge.retry_attempts_count > 0:
                raise GraphMappingError(
                    MappingFailure.UNSUPPORTED_RETRY, edge.target_identifier
                )

    def _ordered_nodes(
        self,
        nodes: dict[str, AnyNode],
        edges: list[Edge],
        client_identifier: str,
    ) -> list[str]:
        """Check cycles and reachability with a deterministic topological sort."""
        incoming: dict[str, int] = {identifier: 0 for identifier in nodes}
        outgoing: dict[str, list[str]] = {identifier: [] for identifier in nodes}
        edge: Edge
        for edge in edges:
            incoming[edge.target_identifier] += 1
            outgoing[edge.source_identifier].append(edge.target_identifier)

        available: list[str] = [
            identifier for identifier, count in incoming.items() if count == 0
        ]
        available.sort()
        result: list[str] = []
        while available:
            current: str = heappop(available)
            result.append(current)
            target: str
            for target in sorted(outgoing[current]):
                incoming[target] -= 1
                if incoming[target] == 0:
                    heappush(available, target)
        if len(result) != len(nodes):
            raise GraphMappingError(MappingFailure.CYCLE, client_identifier)

        reachable: set[str] = {client_identifier}
        queue: list[str] = [client_identifier]
        while queue:
            current = queue.pop()
            for target in outgoing[current]:
                if target not in reachable:
                    reachable.add(target)
                    queue.append(target)
        if reachable != set(nodes):
            missing: str = sorted(set(nodes) - reachable)[0]
            raise GraphMappingError(MappingFailure.DISCONNECTED, missing)
        return result

    def _map_resource(self, node: AnyNode) -> SimulatedResource:
        """Require explicitly known service capacity for every resource."""
        if isinstance(node, MessageBrokerNode):
            raise GraphMappingError(MappingFailure.UNSUPPORTED_BROKER, node.identifier)
        if not isinstance(node, CapacityNode):
            raise GraphMappingError(
                MappingFailure.INVALID_CLIENT_COUNT, node.identifier
            )
        if node.service_channels_per_replica is None:
            raise GraphMappingError(
                MappingFailure.SERVICE_CHANNELS_UNKNOWN, node.identifier
            )
        cache_probability: float | None = (
            node.cache_hit_rate_probability if isinstance(node, CacheNode) else None
        )
        return SimulatedResource(
            identifier=node.identifier,
            node_type=node.node_type,
            replicas_count=node.replicas_count,
            service_channels_per_replica=node.service_channels_per_replica,
            maximum_concurrency_per_replica=node.maximum_concurrency,
            maximum_queue_size_per_replica=node.maximum_queue_size,
            mean_service_seconds=node.mean_processing_time_milliseconds / 1000.0,
            std_service_seconds=node.standard_deviation_processing_time / 1000.0,
            cache_hit_probability=cache_probability,
        )
