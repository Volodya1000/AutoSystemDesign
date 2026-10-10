"""Reusable prompt fragments; all LLM-facing text lives in this package.

Domain vocabularies (node types, protocols, allowed connections) are
derived automatically, not hardcoded.
"""

from typing import Final

from domain.models import protocols as domain_protocols
from domain.models.enums import NodeType
from domain.models.protocols import ConnectionProtocol
from domain.models.scenarios import DesignScenario
from domain.specifications.rules import DEFAULT_ALLOWED_CONNECTION_TYPES

STRUCTURED_OUTPUT_SYSTEM_PROMPT: Final[str] = (
    "You are a senior software architect that designs distributed system topologies. "
    "You always answer with EXACTLY ONE valid JSON object. Your response MUST begin "
    "with the '{' character and MUST end with the '}' character: no markdown, no code "
    "fences, no comments, no explanations, no thinking out loud, and no text before "
    "or after the JSON object. Keep the JSON compact: one node or edge per line, "
    "no extra fields."
)

# Auto-discovery instead of a hand-maintained list: every ConnectionProtocol
# singleton exported by the domain module is picked up automatically, so a
# new protocol constant added to the domain requires no change here.
_KNOWN_PROTOCOLS: Final[tuple[ConnectionProtocol, ...]] = tuple(
    sorted(
        (
            value
            for value in vars(domain_protocols).values()
            if isinstance(value, ConnectionProtocol)
        ),
        key=lambda protocol: protocol.name,
    )
)
_PROTOCOL_DESCRIPTIONS: Final[str] = ", ".join(
    f"{protocol.name} (is_asynchronous={str(protocol.is_asynchronous).lower()})"
    for protocol in _KNOWN_PROTOCOLS
)
_NODE_TYPE_VALUES: Final[str] = ", ".join(node_type.value for node_type in NodeType)

OUTPUT_HARD_RULES: Final[str] = (
    "Hard rules:\n"
    "1. Every identifier is unique across the graph and written in snake_case.\n"
    "2. Every node participates in at least one edge: isolated nodes are forbidden.\n"
    "3. The topology is a strict DAG: cycles are forbidden.\n"
    "4. Every edge matches one of the allowed source -> target transitions.\n"
    '5. Every node except "client" must provide all capacity fields with valid values.\n'
    '6. Include a "client" node as the entry point of user traffic.\n'
    "7. Do not add fields that are not defined in the output format above."
)

FEW_SHOT_GRAPH_JSON: Final[str] = """{
  "nodes": [
    {"identifier": "web_client", "node_type": "client"},
    {"identifier": "edge_lb", "node_type": "load_balancer", "maximum_concurrency": 1000, "maximum_queue_size": 1000, "mean_processing_time_milliseconds": 1.0, "standard_deviation_processing_time": 0.5, "monthly_cost_usd": 20.0},
    {"identifier": "orders_api", "node_type": "compute", "maximum_concurrency": 200, "maximum_queue_size": 500, "mean_processing_time_milliseconds": 15.0, "standard_deviation_processing_time": 3.0, "monthly_cost_usd": 80.0},
    {"identifier": "orders_db", "node_type": "database", "maximum_concurrency": 150, "maximum_queue_size": 1000, "mean_processing_time_milliseconds": 8.0, "standard_deviation_processing_time": 2.0, "monthly_cost_usd": 120.0}
  ],
  "edges": [
    {"source_identifier": "web_client", "target_identifier": "edge_lb", "protocol": {"name": "sync_rest_http", "is_asynchronous": false}, "network_latency_milliseconds": 5.0},
    {"source_identifier": "edge_lb", "target_identifier": "orders_api", "protocol": {"name": "sync_grpc", "is_asynchronous": false}, "network_latency_milliseconds": 2.0},
    {"source_identifier": "orders_api", "target_identifier": "orders_db", "protocol": {"name": "sync_database_tcp", "is_asynchronous": false}, "network_latency_milliseconds": 1.0}
  ]
}"""


def render_scenario_summary(scenario: DesignScenario) -> str:
    """Renders the typed scenario into prompt text."""
    lines: list[str] = [
        f"Scenario: {scenario.identifier}",
        f"Description: {scenario.description}",
        "Workload:",
        (
            f"- Baseline load: {scenario.workload.baseline_requests_per_second} "
            "requests per second"
        ),
        (
            f"- Peak load: {scenario.workload.peak_requests_per_second} "
            "requests per second"
        ),
        (
            f"- Read ratio: {scenario.workload.read_ratio:.2f}, "
            f"write ratio: {scenario.workload.write_ratio:.2f}"
        ),
    ]
    if scenario.requirements:
        lines.append("Requirements that the design must satisfy:")
        lines.extend(
            f"- {requirement.model_dump_json()}"
            for requirement in scenario.requirements
        )
    if scenario.allowed_node_types is not None:
        allowed: str = ", ".join(
            sorted(node_type.value for node_type in scenario.allowed_node_types)
        )
        lines.append(f"Allowed node types (use ONLY these): {allowed}")
    return "\n".join(lines)


def render_output_schema() -> str:
    """Compact hand-written schema; deliberately NOT model_json_schema().

    The discriminated-union JSON schema is unreadable for a small local model.
    """
    return (
        'Output format: a single JSON object with exactly two keys, "nodes" and "edges".\n'
        "\n"
        "Node object:\n"
        '- "identifier": string, unique in the graph, snake_case (example: "orders_api");\n'
        f'- "node_type": one of: {_NODE_TYPE_VALUES};\n'
        '- "replicas_count": integer >= 1, optional (default 1);\n'
        '- capacity fields, REQUIRED for every node_type except "client":\n'
        '    "maximum_concurrency": integer > 0,\n'
        '    "maximum_queue_size": integer >= 0,\n'
        '    "mean_processing_time_milliseconds": number > 0,\n'
        '    "standard_deviation_processing_time": number >= 0,\n'
        '    "monthly_cost_usd": number >= 0;\n'
        '- optional type-specific fields: "database_role" ("primary" or "replica") and '
        '"shards_count" (integer >= 1) for database; "cache_hit_rate_probability" '
        '(number in [0, 1]) for cache; "retention_period_hours" (integer >= 0) for '
        "message_broker.\n"
        "\n"
        "Edge object:\n"
        '- "source_identifier" and "target_identifier": identifiers of nodes declared '
        'in "nodes";\n'
        f'- "protocol": object with exactly two fields: "name" (one of: {_PROTOCOL_DESCRIPTIONS}) '
        'and "is_asynchronous": boolean matching the chosen protocol;\n'
        '- "network_latency_milliseconds": number >= 0.\n'
        "\n"
        "Do not add any other fields: unknown fields are rejected."
    )


def render_allowed_connections() -> str:
    """Renders the connection whitelist straight from the domain rule set."""
    lines: list[str] = [
        (
            "Allowed node type transitions (an edge may connect ONLY these "
            "source -> target pairs):"
        )
    ]
    allowed_pairs: list[tuple[str, str]] = sorted(
        (connection.source.value, connection.target.value)
        for connection in DEFAULT_ALLOWED_CONNECTION_TYPES
    )
    lines.extend(f"- {source} -> {target}" for source, target in allowed_pairs)
    return "\n".join(lines)
