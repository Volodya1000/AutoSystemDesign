"""Run reproducible performance-analysis demonstrations without an LLM.

Four real scenario YAML files enter PipelineRunner with a fixed C4 outcome.
The fixture architectures are synthetic examples, not AI-generated designs.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import yaml

from application.pipeline.runner import PipelineRunner
from application.pipeline.stages.performance_analysis import PerformanceAnalysisStage
from domain.models.edges import Edge
from domain.models.enums import EdgeRoutingMode
from domain.models.nodes import CacheNode, ClientNode, ComputeNode, DatabaseNode
from domain.models.protocols import (
    ASYNCHRONOUS_MESSAGE_QUEUE,
    SYNCHRONOUS_REST_HTTP,
    ConnectionProtocol,
)
from domain.models.scenarios import DesignScenario
from domain.models.topology import ArchitectureGraph
from infrastructure.performance_analysis.offline_c4_stage import OfflineC4Stage
from infrastructure.performance_analysis.pdf_renderer import (
    PerformanceReportPdfRenderer,
)
from infrastructure.persistence.artifact_writer import FileSystemArtifactWriter
from infrastructure.reporting.adapters import LoggingPipelineReporter

_SCENARIOS: tuple[str, ...] = (
    "checkout_baseline",
    "catalog_read_heavy",
    "notifications_spiky",
    "helpdesk_no_workload",
)
_LOGGER = logging.getLogger("performance.demo")


def _compute(identifier: str, mean_ms: float, channels: int) -> ComputeNode:
    """Construct a compute node with explicitly known parallel channels."""
    return ComputeNode(
        identifier=identifier,
        maximum_concurrency=channels * 2,
        maximum_queue_size=500,
        service_channels_per_replica=channels,
        mean_processing_time_milliseconds=mean_ms,
        standard_deviation_processing_time=mean_ms,
        monthly_cost_usd=60.0,
    )


def _database(identifier: str, mean_ms: float, channels: int) -> DatabaseNode:
    """Construct a database with known capacity and service channels."""
    return DatabaseNode(
        identifier=identifier,
        maximum_concurrency=channels * 2,
        maximum_queue_size=500,
        service_channels_per_replica=channels,
        mean_processing_time_milliseconds=mean_ms,
        standard_deviation_processing_time=mean_ms,
        monthly_cost_usd=100.0,
    )


def _edge(
    source: str,
    target: str,
    *,
    mode: EdgeRoutingMode = EdgeRoutingMode.ALTERNATIVE,
    protocol: ConnectionProtocol = SYNCHRONOUS_REST_HTTP,
) -> Edge:
    """Connect two fixture nodes using the real typed edge model."""
    return Edge(
        source_identifier=source,
        target_identifier=target,
        routing_mode=mode,
        protocol=protocol,
        network_latency_milliseconds=1.0,
    )


def _checkout_graph() -> ArchitectureGraph:
    """Model checkout followed by concurrent payment and stock reservation."""
    return ArchitectureGraph(
        nodes=[
            ClientNode(identifier="client"),
            _compute("checkout_api", 8.0, 4),
            _compute("payment_service", 20.0, 3),
            _database("inventory_db", 12.0, 4),
        ],
        edges=[
            _edge("client", "checkout_api"),
            _edge("checkout_api", "payment_service", mode=EdgeRoutingMode.FAN_OUT),
            _edge("checkout_api", "inventory_db", mode=EdgeRoutingMode.FAN_OUT),
        ],
    )


def _catalog_graph() -> ArchitectureGraph:
    """Exercise read-heavy cache and database miss-fallback allocation."""
    return ArchitectureGraph(
        nodes=[
            ClientNode(identifier="client"),
            _compute("catalog_api", 4.0, 8),
            CacheNode(
                identifier="catalog_cache",
                maximum_concurrency=32,
                maximum_queue_size=500,
                service_channels_per_replica=16,
                mean_processing_time_milliseconds=2.0,
                standard_deviation_processing_time=2.0,
                monthly_cost_usd=30.0,
                cache_hit_rate_probability=0.95,
            ),
            _database("catalog_db", 10.0, 8),
        ],
        edges=[
            _edge("client", "catalog_api"),
            _edge("catalog_api", "catalog_cache"),
            _edge("catalog_api", "catalog_db"),
        ],
    )


def _notifications_graph() -> ArchitectureGraph:
    """Exercise an asynchronous branch excluded from synchronous latency."""
    return ArchitectureGraph(
        nodes=[
            ClientNode(identifier="client"),
            _compute("notifications_api", 4.0, 8),
            _compute("delivery_worker", 18.0, 10),
            _database("outbox_db", 6.0, 6),
        ],
        edges=[
            _edge("client", "notifications_api"),
            _edge(
                "notifications_api",
                "delivery_worker",
                mode=EdgeRoutingMode.FAN_OUT,
                protocol=ASYNCHRONOUS_MESSAGE_QUEUE,
            ),
            _edge("notifications_api", "outbox_db", mode=EdgeRoutingMode.FAN_OUT),
        ],
    )


def _helpdesk_graph() -> ArchitectureGraph:
    """Model a valid graph with intentionally absent workload observations."""
    return ArchitectureGraph(
        nodes=[
            ClientNode(identifier="client"),
            _compute("helpdesk_api", 12.0, 2),
            _database("ticket_db", 8.0, 2),
        ],
        edges=[
            _edge("client", "helpdesk_api"),
            _edge("helpdesk_api", "ticket_db"),
        ],
    )


def _scenario_graph(scenario_identifier: str) -> ArchitectureGraph:
    """Select an explicit fixture matching each real acceptance YAML."""
    match scenario_identifier:
        case "checkout_baseline":
            return _checkout_graph()
        case "catalog_read_heavy":
            return _catalog_graph()
        case "notifications_spiky":
            return _notifications_graph()
        case "helpdesk_no_workload":
            return _helpdesk_graph()
        case _:
            message: str = f"Unknown offline demo scenario: {scenario_identifier}"
            raise ValueError(message)


def main() -> int:
    """Validate each YAML and generate its real C4, JSON and PDF artifacts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    writer = FileSystemArtifactWriter()

    for identifier in _SCENARIOS:
        yaml_path: Path = Path("scenarios/performance") / f"{identifier}.yaml"
        scenario: DesignScenario = DesignScenario.model_validate(
            yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        )
        directory: Path = args.out_dir / identifier
        graph: ArchitectureGraph = _scenario_graph(identifier)
        _LOGGER.info("Scenario=%s: FIXED synthetic C4 fixture; NO LLM", identifier)
        runner = PipelineRunner(
            stages=[
                OfflineC4Stage(graph),
                PerformanceAnalysisStage(pdf_renderer=PerformanceReportPdfRenderer()),
            ],
            reporter=LoggingPipelineReporter(),
        )
        exit_code: int = runner.run(scenario, directory, writer)
        if exit_code != 0:
            _LOGGER.error("Pipeline failed for scenario=%s", identifier)
            return exit_code
        _LOGGER.info("Generated JSON and PDF for %s in %s", identifier, directory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
