"""Analyze a fixed architecture with explicit profiles without contacting an LLM."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from application.pipeline.runner import PipelineRunner
from application.pipeline.stages.performance_analysis import PerformanceAnalysisStage
from domain.models.scenarios import DesignScenario
from domain.models.topology import ArchitectureGraph
from domain.service_profiles import ProfileApplication, ServiceProfileCatalog
from domain.specifications.broker_consumer_validator import (
    MessageBrokerConsumerValidator,
)
from domain.specifications.cache_usage_validator import CacheUsageValidator
from domain.specifications.capacity_validator import CapacitySaturationValidator
from domain.specifications.structural_validator import StructuralTopologyValidator
from infrastructure.performance_analysis.offline_c4_stage import OfflineC4Stage
from infrastructure.performance_analysis.pdf_renderer import (
    PerformanceReportPdfRenderer,
)
from infrastructure.persistence.artifact_writer import FileSystemArtifactWriter
from infrastructure.reporting import LoggingPipelineReporter

if TYPE_CHECKING:
    from collections.abc import Sequence

_LOGGER: logging.Logger = logging.getLogger(__name__)


def main(argv: Sequence[str] | None = None) -> int:
    """Bind documented profiles and run the real deterministic report stage."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args: argparse.Namespace = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    try:
        graph: ArchitectureGraph = ArchitectureGraph.model_validate_json(
            args.graph.read_text(encoding="utf-8")
        )
        scenario: DesignScenario = DesignScenario.model_validate(
            yaml.safe_load(args.scenario.read_text(encoding="utf-8"))
        )
        catalog: ServiceProfileCatalog = ServiceProfileCatalog.model_validate_json(
            args.profiles.read_text(encoding="utf-8")
        )
    except (OSError, ValueError, yaml.YAMLError):
        _LOGGER.exception("Invalid architecture, scenario or profile catalog")
        return 2
    binding: ProfileApplication = catalog.apply(graph)
    errors = [
        *StructuralTopologyValidator().validate(binding.graph).errors,
        *MessageBrokerConsumerValidator().validate(binding.graph).errors,
        *CacheUsageValidator().validate(binding.graph).errors,
        *CapacitySaturationValidator().validate(binding.graph, scenario).errors,
    ]
    if errors:
        for error in errors:
            _LOGGER.error("%s", error.message)
        return 1
    writer: FileSystemArtifactWriter = FileSystemArtifactWriter()
    writer.write_text(
        args.out_dir / f"{scenario.identifier}_service_profiles.json",
        ServiceProfileCatalog(by_node_id=binding.applied).model_dump_json(indent=2),
    )
    runner: PipelineRunner = PipelineRunner(
        stages=[
            OfflineC4Stage(binding.graph),
            PerformanceAnalysisStage(pdf_renderer=PerformanceReportPdfRenderer()),
        ],
        reporter=LoggingPipelineReporter(),
    )
    return runner.run(scenario, args.out_dir, writer)


if __name__ == "__main__":
    raise SystemExit(main())
