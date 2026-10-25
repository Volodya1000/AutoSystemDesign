"""Exercise the thin BRD CLI and document workflow without a live LLM."""

import argparse
import json
from pathlib import Path

import pytest
import yaml
from pydantic import SecretStr

from application.pipeline.outcome import StageDiagnostics, StageOutcome, StageStatus
from application.pipeline.stage import StageId
from config.llm import LlmSettings, StructuredOutputMode
from config.root import AppSettings
from domain.models.scenarios import DesignScenario
from domain.scenario_extraction import DocumentScenarioResult
from infrastructure import document_generation as workflow
from infrastructure.pipeline_execution import PipelineExecutionOptions
from scripts import generate_from_brd as cli
from scripts._cli_arguments import diagram_server

pytestmark = pytest.mark.unit


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> AppSettings:
    settings = AppSettings(
        base_url="http://localhost:1234/v1",
        api_key=SecretStr("test"),
        llm=LlmSettings(
            model="openai/test",
            temperature=0,
            max_tokens=100,
            timeout_seconds=1,
            structured_output_mode=StructuredOutputMode.PROMPT,
        ),
    )
    monkeypatch.setattr(workflow, "load_app_settings", lambda: settings)
    return settings


@pytest.mark.parametrize(
    "value",
    [
        "auto",
        "plantuml",
        "kroki",
        "http://localhost:8080",
        "https://uml.example",
    ],
)
def test_diagram_server_accepts_presets_and_absolute_urls(value: str) -> None:
    assert diagram_server(value) == value


@pytest.mark.parametrize("value", ["localhost:8080", "file:///tmp/uml", "unknown"])
def test_diagram_server_rejects_ambiguous_values(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="auto, plantuml, kroki"):
        diagram_server(value)


def test_document_stem_selects_default_output_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[workflow.DocumentGenerationOptions] = []

    def generate(options: workflow.DocumentGenerationOptions) -> int:
        captured.append(options)
        return 0

    monkeypatch.setattr(cli, "generate_from_document", generate)

    assert cli.main(["--document", "examples/requirements/orders.md"]) == 0
    assert captured[0].out_dir == Path("output/orders")


@pytest.mark.parametrize("pipeline_code", [0, 1, 2])
def test_generate_preserves_evidence_options_and_pipeline_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    configured: AppSettings,
    pipeline_code: int,
) -> None:
    out = tmp_path / "result"
    profiles = tmp_path / "profiles.json"
    profiles.write_text("{}", encoding="utf-8")
    result = DocumentScenarioResult(
        scenario=DesignScenario(identifier="orders", description="Track orders"),
        field_evidence={"description": "Track orders"},
        issues=[],
        is_relevant=True,
        source_name="brd.md",
    )

    class FakeService:
        def extract_file(self, _path: Path) -> DocumentScenarioResult:
            return result

    monkeypatch.setattr(
        workflow, "build_document_scenario_service", lambda _settings: FakeService()
    )
    captured: dict[str, object] = {}

    def execute(
        scenario: DesignScenario,
        settings: AppSettings,
        options: PipelineExecutionOptions,
        *,
        reporter: workflow.RunReporter,
    ) -> int:
        captured.update(scenario=scenario, settings=settings, options=options)
        artifact_dir = out / "artifacts"
        artifact_dir.mkdir()
        (artifact_dir / "orders_c4.json").write_text("{}", encoding="utf-8")
        reporter.report(
            [
                StageOutcome(
                    name=StageId.C4,
                    status=StageStatus.PARTIAL,
                    duration_seconds=1,
                    total_tokens=10,
                    diagnostics=StageDiagnostics(warnings=("Renderer unavailable",)),
                )
            ]
        )
        return pipeline_code

    monkeypatch.setattr(workflow, "execute_pipeline", execute)
    code = cli.main(
        [
            "--document",
            "brd.md",
            "--out-dir",
            str(out),
            "--diagram-server",
            "http://localhost:8080",
            "--diagram-format",
            "svg",
            "--profiles",
            str(profiles),
        ]
    )
    assert code == pipeline_code
    assert captured["scenario"] == result.scenario
    assert captured["settings"] is configured
    options = captured["options"]
    assert isinstance(options, PipelineExecutionOptions)
    assert options.diagram_server == "http://localhost:8080"
    assert options.diagram_format.value == "svg"
    evidence = json.loads((out / "requirements.evidence.json").read_text("utf-8"))
    assert evidence["field_evidence"] == result.field_evidence
    scenario = yaml.safe_load((out / "scenario.yaml").read_text("utf-8"))
    assert DesignScenario.model_validate(scenario) == result.scenario
    report = json.loads((out / "run.json").read_text("utf-8"))
    assert report["exit_code"] == pipeline_code
    assert report["performance_input_mode"] == "explicit_service_profiles"
    assert report["stages"][0]["warnings"] == ["Renderer unavailable"]


def test_unverified_document_stops_before_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, configured: AppSettings
) -> None:
    _ = configured

    class FakeService:
        def extract_file(self, _path: Path) -> DocumentScenarioResult:
            return DocumentScenarioResult(
                scenario=None,
                field_evidence={},
                issues=[],
                is_relevant=False,
                source_name="brd.md",
            )

    monkeypatch.setattr(
        workflow, "build_document_scenario_service", lambda _settings: FakeService()
    )
    out = tmp_path / "result"
    assert cli.main(["--document", "brd.md", "--out-dir", str(out)]) == 1
    assert (out / "requirements.evidence.json").exists()
    assert not (out / "scenario.yaml").exists()


def test_existing_output_is_never_overwritten(tmp_path: Path) -> None:
    sentinel = tmp_path / "scenario.yaml"
    sentinel.write_text("previous run", encoding="utf-8")
    assert cli.main(["--document", "brd.md", "--out-dir", str(tmp_path)]) == 2
    assert sentinel.read_text("utf-8") == "previous run"


def test_missing_document_creates_failure_report(
    tmp_path: Path, configured: AppSettings
) -> None:
    _ = configured
    out = tmp_path / "result"
    assert cli.main(["--document", "absent.md", "--out-dir", str(out)]) == 2
    report = json.loads((out / "run.json").read_text("utf-8"))
    assert report["status"] == "failed"
