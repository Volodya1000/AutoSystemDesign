"""Rendering of the architecture-graph output contract for prompts.

Contains the structural JSON Schema fragment, the allowed-connection
whitelist, the system prompt for structured output, and the few-shot
example. All of these change together with the ArchitectureGraph model,
so they live in one module.
"""

import json
from typing import Final

from domain.models.topology import ArchitectureGraph
from domain.specifications.rules import DEFAULT_ALLOWED_CONNECTION_TYPES
from infrastructure.prompts.fragments_protocols import render_known_protocols

STRUCTURED_OUTPUT_SYSTEM_PROMPT: Final[str] = (
    "You are a senior software architect that designs distributed system topologies. "
    "You always answer with EXACTLY ONE valid JSON object. Your response MUST begin "
    "with the '{' character and MUST end with the '}' character: no markdown, no code "
    "fences, no comments, no explanations, no thinking out loud, and no text before "
    "or after the JSON object. Keep the JSON compact: one node or edge per line, "
    "no extra fields."
)

OUTPUT_HARD_RULES: Final[str] = (
    "Hard rules:\n"
    "1. Every identifier is unique across the graph and written in snake_case.\n"
    "2. Every node participates in at least one edge: isolated nodes are forbidden.\n"
    "3. The topology is a strict DAG: cycles are forbidden.\n"
    "4. Every edge matches one of the allowed source -> target transitions.\n"
    '5. Every node except "client" must provide all capacity fields '
    'with valid values.\n'
    '6. Include a "client" node as the entry point of user traffic.\n'
    "7. Do not add fields that are not defined in the output format above.\n"
    "8. Every message_broker node is a routing bridge with DISTINCT ends:\n"
    "   - at least one incoming edge from a compute node (the producer);\n"
    "   - at least one outgoing edge to a DIFFERENT compute node (the consumer).\n"
    "   The producer and the consumer MUST be different compute nodes. A "
    "broker cannot route a message back to its own producer: that forms a "
    "cycle, which is forbidden by rule 3. To add asynchronous decoupling, "
    "introduce a dedicated worker compute node behind the broker "
    "(producer -> broker -> worker), not a loop back to the producer. For "
    "example, message_processor -> message_broker -> notification_worker "
    "is valid; message_processor -> message_broker -> message_processor "
    "and message_broker -> message_broker are invalid. If you do not need "
    "async decoupling, do not add a broker at all.\n"
    "9. Every cache node MUST be on a real read path:\n"
    "   - at least one SYNCHRONOUS incoming edge from a compute node "
    "(the read attempt);\n"
    "   - that SAME compute node MUST also have another outgoing edge "
    "to the database (the cache-miss fallback).\n"
    "   Canonical pattern: compute -> cache (synchronous read) AND "
    "compute -> database (synchronous fallback). Both edges originate "
    "from the compute node. NEVER connect cache -> database: cache is "
    "not a caller and must not own the fallback path.\n"
    "   An async-only edge into a cache is a write-only sink: the cache "
    "receives data but nobody reads it, and cache_hit_rate is dead. "
    "Either use the canonical read + fallback pattern, or remove the cache.\n"
    "10. Before returning JSON, check every edge against the whitelist and "
    "re-check cache directionality: cache -> database is forbidden.\n"
    "11. Before returning JSON, trace every path through each message_broker. "
    "Confirm that its producer and consumer are different compute nodes, "
    "and that no edge creates a cycle or a self-loop."
)

FEW_SHOT_GRAPH_JSON: Final[str] = """{
  "nodes": [
    {"identifier": "web_client", "node_type": "client"},
    {"identifier": "edge_lb", "node_type": "load_balancer",
     "maximum_concurrency": 1000, "maximum_queue_size": 1000,
     "mean_processing_time_milliseconds": 1.0,
     "standard_deviation_processing_time": 0.5, "monthly_cost_usd": 20.0},
    {"identifier": "orders_api", "node_type": "compute",
     "maximum_concurrency": 200, "maximum_queue_size": 500,
     "mean_processing_time_milliseconds": 15.0,
     "standard_deviation_processing_time": 3.0, "monthly_cost_usd": 80.0},
    {"identifier": "orders_db", "node_type": "database",
     "maximum_concurrency": 150, "maximum_queue_size": 1000,
     "mean_processing_time_milliseconds": 8.0,
     "standard_deviation_processing_time": 2.0, "monthly_cost_usd": 120.0}
  ],
  "edges": [
    {"source_identifier": "web_client", "target_identifier": "edge_lb",
     "protocol": {"name": "sync_rest_http", "is_asynchronous": false},
     "network_latency_milliseconds": 5.0},
    {"source_identifier": "edge_lb", "target_identifier": "orders_api",
     "protocol": {"name": "sync_grpc", "is_asynchronous": false},
     "network_latency_milliseconds": 2.0},
    {"source_identifier": "orders_api", "target_identifier": "orders_db",
     "protocol": {"name": "sync_database_tcp", "is_asynchronous": false},
     "network_latency_milliseconds": 1.0}
  ]
}"""


def render_output_schema() -> str:
    """Renders the output contract for the architecture graph.

    The structural part is generated from ArchitectureGraph.model_json_schema()
    so any change to the pydantic models is reflected in the prompt with no
    extra edits (single source of truth). Field descriptions declared with
    Field(description=...) carry through into the schema automatically.

    The protocol-value list is appended separately because the schema only
    knows ConnectionProtocol.name as a plain string; without it, the model
    would invent arbitrary protocol names.
    """
    schema_text: str = json.dumps(ArchitectureGraph.model_json_schema(), indent=2)
    return (
        "Output format: a single JSON object matching the following JSON Schema "
        "(generated from the domain models).\n"
        f"{schema_text}\n\n"
        f"{render_known_protocols()}\n\n"
        "Do not add any other fields: unknown fields are rejected."
    )


def render_allowed_connections() -> str:
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
