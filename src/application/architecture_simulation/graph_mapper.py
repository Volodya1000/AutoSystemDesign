"""Convert validated C4 topology into typed simulation input without an LLM."""

from application.architecture_simulation.graph_mapping_errors import GraphMappingError
from application.architecture_simulation.mapping_failures import MappingFailure
from application.architecture_simulation.simulation_graph_validator import SimulationGraphValidator
from domain.architecture_simulation.graph_plan import GraphSimulationPlan, SimulatedConnection, SimulatedResource
from domain.models.edges import Edge
from domain.models.nodes import CacheNode, CapacityNode, ClientNode, MessageBrokerNode
from domain.models.scenarios import DesignScenario, WorkloadProfile
from domain.models.topology import AnyNode, ArchitectureGraph


class ArchitectureSimulationPlanMapper:
    """Produce a deterministic, strictly supported simulation graph."""

    def map(
        self, graph: ArchitectureGraph, scenario: DesignScenario
    ) -> GraphSimulationPlan:
        """Validate topology before converting timings from milliseconds."""
        workload: WorkloadProfile | None = scenario.workload
        if workload is None:
            raise GraphMappingError(
                MappingFailure.MISSING_WORKLOAD, scenario.identifier
            )

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
        validator: SimulationGraphValidator = SimulationGraphValidator()
        validator.validate_edges(edges, nodes)
        order: list[str] = validator.ordered_nodes(nodes, edges, client_identifier)
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
