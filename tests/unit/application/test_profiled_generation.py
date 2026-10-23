"""Keep persisted architecture, applied profiles and calculations consistent."""

import json
from pathlib import Path

import pytest
from pydantic import SecretStr

from application.pipeline.context import StageContext
from application.pipeline.outcome import StageStatus
from application.pipeline.stages.c4 import C4Stage
from application.services.design_generation_service import DesignGenerationService
from application.tasks import DesignProposal, DesignTask
from application.usage import TokenUsage
from config.llm import LlmSettings, StructuredOutputMode
from config.root import AppSettings
from domain.models.enums import NodeType
from domain.models.scenarios import DesignScenario
from domain.models.topology import ArchitectureGraph
from domain.service_profiles import ServiceProfileCatalog
from domain.specifications.structural_validator import StructuralTopologyValidator
from infrastructure.reporting import LoggingGenerationReporter
from scripts.analyze_profiled_architecture import main
from tests.factories import (
    create_test_compute_node,
    create_test_edge,
    create_test_node,
    create_test_service_profile,
)
from tests.unit.in_memory_writer import InMemoryWriter

pytestmark = pytest.mark.unit
_EXAMPLES: Path = Path(__file__).resolve().parents[3] / "examples/performance"


class FixedDesigner:
    """Supply a fixed external proposal to exercise the actual design service."""

    def propose(self, task: DesignTask) -> DesignProposal:
        _ = task
        return DesignProposal(
            graph=ArchitectureGraph(
                nodes=[
                    create_test_node("client", NodeType.CLIENT),
                    create_test_compute_node("orders", cost=9999),
                ],
                edges=[create_test_edge("client", "orders")],
            ),
            raw_content="{}",
            usage=TokenUsage(),
        )


def test_c4_persists_the_profiled_graph_and_its_exact_sources(tmp_path: Path) -> None:
    catalog: ServiceProfileCatalog = ServiceProfileCatalog(
        by_node_type={NodeType.COMPUTE: create_test_service_profile()}
    )
    writer: InMemoryWriter = InMemoryWriter()
    stage: C4Stage = C4Stage(
        service=DesignGenerationService(
            designer=FixedDesigner(),
            validators=[StructuralTopologyValidator()],
            max_attempts=1,
            service_profiles=catalog,
        ),
        renderer=None,
        reporter=LoggingGenerationReporter(),
        service_profiles=catalog,
    )
    outcome = stage.run(
        StageContext(
            scenario=DesignScenario(identifier="orders", description="Orders"),
            out_dir=tmp_path,
            writer=writer,
            upstream={},
        )
    )
    assert outcome.status is StageStatus.SUCCEEDED
    assert outcome.payload is not None
    files: dict[str, str] = {path.name: text for path, text in writer.writes}
    assert (
        ArchitectureGraph.model_validate_json(files["orders_c4.json"])
        == outcome.payload
    )
    manifest: ServiceProfileCatalog = ServiceProfileCatalog.model_validate_json(
        files["orders_service_profiles.json"]
    )
    assert manifest.by_node_id["orders"] == create_test_service_profile()
    assert not manifest.by_node_type


def test_profile_path_in_settings_is_validated(tmp_path: Path) -> None:
    profile_path: Path = tmp_path / "profiles.json"
    catalog: ServiceProfileCatalog = ServiceProfileCatalog(
        by_node_type={NodeType.COMPUTE: create_test_service_profile()}
    )
    profile_path.write_text(catalog.model_dump_json(), encoding="utf-8")
    settings: AppSettings = AppSettings.model_validate(
        {
            "base_url": "http://localhost:1234/v1",
            "api_key": SecretStr("fake"),
            "llm": LlmSettings(
                model="test",
                temperature=0,
                max_tokens=64,
                timeout_seconds=5,
                structured_output_mode=StructuredOutputMode.PROMPT,
            ),
            "service_profiles": str(profile_path),
        }
    )
    assert settings.service_profiles == catalog


def test_offline_command_creates_finite_latency_report_and_profile_manifest(
    tmp_path: Path,
) -> None:
    exit_code: int = main(
        [
            "--graph",
            str(_EXAMPLES / "online_store_graph.json"),
            "--scenario",
            str(_EXAMPLES / "online_store_scenario.yaml"),
            "--profiles",
            str(_EXAMPLES / "online_store_profiles.json"),
            "--out-dir",
            str(tmp_path),
        ]
    )
    assert exit_code == 0
    report = json.loads(
        (tmp_path / "online_store_demo_performance_analysis.json").read_text()
    )
    assert report["estimated_longest_synchronous_path_mean_milliseconds"] > 0
    assert report["critical_path_node_identifiers"]
    assert (tmp_path / "online_store_demo_service_profiles.json").is_file()
    assert (tmp_path / "online_store_demo_performance_analysis.pdf").is_file()


def test_offline_command_rejects_missing_inputs(tmp_path: Path) -> None:
    assert (
        main(
            [
                "--graph",
                "missing",
                "--scenario",
                "missing",
                "--profiles",
                "missing",
                "--out-dir",
                str(tmp_path),
            ]
        )
        == 2
    )


def test_offline_command_rejects_unmapped_capacity_nodes(tmp_path: Path) -> None:
    catalog: Path = tmp_path / "empty.json"
    catalog.write_text("{}", encoding="utf-8")
    assert (
        main(
            [
                "--graph",
                str(_EXAMPLES / "online_store_graph.json"),
                "--scenario",
                str(_EXAMPLES / "online_store_scenario.yaml"),
                "--profiles",
                str(catalog),
                "--out-dir",
                str(tmp_path),
            ]
        )
        == 1
    )
