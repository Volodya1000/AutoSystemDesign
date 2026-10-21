# Copyright (c) 2026 Volodya1000
"""Unit tests of the LLM output extraction and parsing."""

import json

import pytest

from application.exceptions.generation_exceptions import DesignProposalParsingError
from application.tasks import JSON_DECODE_ERROR_TYPE
from application.usage import TokenUsage
from domain.models.nodes import ClientNode, ComputeNode, DatabaseNode
from domain.models.protocols import ConnectionProtocol
from infrastructure.design.parser import (
    extract_json_payload,
    parse_architecture_graph,
)

pytestmark = pytest.mark.unit

USAGE: TokenUsage = TokenUsage(prompt_tokens=11, completion_tokens=7)

_VALID_GRAPH: dict[str, object] = {
    "nodes": [
        {"identifier": "web_client", "node_type": "client"},
        {
            "identifier": "orders_api",
            "node_type": "compute",
            "maximum_concurrency": 200,
            "maximum_queue_size": 500,
            "mean_processing_time_milliseconds": 15.0,
            "standard_deviation_processing_time": 3.0,
            "monthly_cost_usd": 80.0,
        },
        {
            "identifier": "orders_db",
            "node_type": "database",
            "maximum_concurrency": 150,
            "maximum_queue_size": 1000,
            "mean_processing_time_milliseconds": 8.0,
            "standard_deviation_processing_time": 2.0,
            "monthly_cost_usd": 120.0,
        },
    ],
    "edges": [
        {
            "source_identifier": "web_client",
            "target_identifier": "orders_api",
            "protocol": {"name": "sync_rest_http", "is_asynchronous": False},
            "network_latency_milliseconds": 5.0,
        },
        {
            "source_identifier": "orders_api",
            "target_identifier": "orders_db",
            "protocol": {"name": "sync_database_tcp", "is_asynchronous": False},
            "network_latency_milliseconds": 1.0,
        },
    ],
}
VALID_GRAPH_JSON: str = json.dumps(_VALID_GRAPH)


class TestExtractJsonPayload:
    def test_plain_json(self) -> None:
        assert extract_json_payload('{"nodes": []}') == '{"nodes": []}'

    def test_json_code_fence(self) -> None:
        assert extract_json_payload('```json\n{"nodes": []}\n```') == '{"nodes": []}'

    def test_plain_code_fence(self) -> None:
        assert extract_json_payload('```\n{"nodes": []}\n```') == '{"nodes": []}'

    def test_think_block_is_removed(self) -> None:
        raw: str = 'Let me think.\n{"nodes": []}'
        assert extract_json_payload(raw) == '{"nodes": []}'

    def test_think_block_with_fence(self) -> None:
        raw: str = 'reasoning\n```json\n{"nodes": []}\n```'
        assert extract_json_payload(raw) == '{"nodes": []}'

    def test_prose_around_json(self) -> None:
        raw: str = 'Here is your graph:\n{"nodes": []}\nHope this helps!'
        assert extract_json_payload(raw) == '{"nodes": []}'

    def test_combined_noise(self) -> None:
        raw: str = (
            "deep reasoning\n"
            'Sure! Here you go:\n```json\n{"nodes": []}\n```\nAnything else?'
        )
        assert extract_json_payload(raw) == '{"nodes": []}'


class TestParseArchitectureGraph:
    def test_valid_payload_maps_to_concrete_node_classes(self) -> None:
        graph = parse_architecture_graph(VALID_GRAPH_JSON, usage=USAGE)
        assert [type(node) for node in graph.nodes] == [
            ClientNode,
            ComputeNode,
            DatabaseNode,
        ]
        assert graph.edges[0].protocol == ConnectionProtocol(
            name="sync_rest_http", is_asynchronous=False
        )

    def test_unknown_node_type_reports_location(self) -> None:
        payload: str = json.dumps(
            {"nodes": [{"identifier": "x", "node_type": "mainframe"}], "edges": []}
        )
        with pytest.raises(DesignProposalParsingError) as exc_info:
            parse_architecture_graph(payload, usage=USAGE)
        details = exc_info.value.failure_details
        assert details
        assert details[0].location.startswith("$.nodes[0]")
        assert details[0].error_type

    def test_broken_json_reports_decode_error_type(self) -> None:
        with pytest.raises(DesignProposalParsingError) as exc_info:
            parse_architecture_graph('{"nodes": [', usage=USAGE)
        details = exc_info.value.failure_details
        assert len(details) == 1
        assert details[0].error_type == JSON_DECODE_ERROR_TYPE
        assert details[0].location == "$"

    def test_missing_required_field_reports_field_path(self) -> None:
        broken: dict[str, object] = {
            "nodes": [
                {"identifier": "web_client", "node_type": "client"},
                {
                    "identifier": "orders_api",
                    "node_type": "compute",
                    "maximum_queue_size": 500,
                    "mean_processing_time_milliseconds": 15.0,
                    "standard_deviation_processing_time": 3.0,
                    "monthly_cost_usd": 80.0,
                },
            ],
            "edges": [],
        }
        with pytest.raises(DesignProposalParsingError) as exc_info:
            parse_architecture_graph(json.dumps(broken), usage=USAGE)
        locations: list[str] = [
            detail.location for detail in exc_info.value.failure_details
        ]
        error_types: set[str] = {
            detail.error_type for detail in exc_info.value.failure_details
        }
        # Pydantic 2.14 and later may include the discriminated-union branch
        # name in the location path. Earlier versions omit it; both paths
        # identify the same field.
        assert any(
            location.startswith("$.nodes[1]")
            and location.endswith(".maximum_concurrency")
            for location in locations
        )
        assert "missing" in error_types

    def test_usage_and_raw_content_are_propagated_into_error(self) -> None:
        usage: TokenUsage = TokenUsage(prompt_tokens=42, completion_tokens=17)
        with pytest.raises(DesignProposalParsingError) as exc_info:
            parse_architecture_graph("not json at all", usage=usage)
        assert exc_info.value.usage == usage
        assert exc_info.value.raw_content == "not json at all"
