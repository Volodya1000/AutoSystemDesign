import json

import pytest

from domain.models.protocols import (
    ASYNCHRONOUS_MESSAGE_QUEUE,
    SYNCHRONOUS_DATABASE_TCP,
    SYNCHRONOUS_GRPC,
    SYNCHRONOUS_REST_HTTP,
)
from domain.models.topology import ArchitectureGraph
from domain.specifications.rules import DEFAULT_ALLOWED_CONNECTION_TYPES
from domain.specifications.structural_validator import StructuralTopologyValidator
from infrastructure.prompts.fragments_schema import (
    FEW_SHOT_GRAPH_JSON,
    OUTPUT_HARD_RULES,
    render_allowed_connections,
    render_output_schema,
)

pytestmark = pytest.mark.unit


class TestFragments:
    def test_render_allowed_connections_covers_default_rule_set(self) -> None:
        rendered: str = render_allowed_connections()
        for connection in DEFAULT_ALLOWED_CONNECTION_TYPES:
            assert f"{connection.source.value} -> {connection.target.value}" in rendered

    def test_schema_lists_all_domain_protocol_singletons(self) -> None:
        schema_text: str = render_output_schema()
        for protocol in (
            SYNCHRONOUS_REST_HTTP,
            SYNCHRONOUS_GRPC,
            SYNCHRONOUS_DATABASE_TCP,
            ASYNCHRONOUS_MESSAGE_QUEUE,
        ):
            assert protocol.name in schema_text

    def test_schema_includes_edge_routing_modes(self) -> None:
        schema_text: str = render_output_schema()

        assert "routing_mode" in schema_text
        assert '"alternative"' in schema_text
        assert '"fan_out"' in schema_text

    def test_schema_requires_performance_channels_for_generated_services(self) -> None:
        schema_text: str = render_output_schema()

        assert "service_channels_per_replica" in schema_text
        assert "never copy maximum_concurrency" in OUTPUT_HARD_RULES

    def test_few_shot_example_is_a_valid_graph(self) -> None:
        graph: ArchitectureGraph = ArchitectureGraph.model_validate(
            json.loads(FEW_SHOT_GRAPH_JSON)
        )
        result = StructuralTopologyValidator().validate(graph)
        assert result.is_successful is True
