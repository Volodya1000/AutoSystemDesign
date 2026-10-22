"""Validate simulation-specific topology and derive a deterministic DAG order."""

from heapq import heappop, heappush

from application.architecture_simulation.graph_mapping_errors import GraphMappingError
from application.architecture_simulation.mapping_failures import MappingFailure
from domain.models.edges import Edge
from domain.models.topology import AnyNode


class SimulationGraphValidator:
    """Validate simulation execution preconditions, not general domain invariants."""

    def validate_edges(self, edges: list[Edge], nodes: dict[str, AnyNode]) -> None:
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

    def ordered_nodes(
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
            missing: str = min(set(nodes) - reachable)
            raise GraphMappingError(MappingFailure.DISCONNECTED, missing)
        return result
