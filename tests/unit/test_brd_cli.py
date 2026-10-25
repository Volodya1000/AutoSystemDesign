"""Exercise document CLI success and failure contracts without a live LLM."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from pydantic import SecretStr

from application.document_scenario_service import DocumentScenarioService
from application.pipeline.outcome import StageDiagnostics, StageOutcome, StageStatus
from application.pipeline.stage import StageId
from config.llm import LlmSettings, StructuredOutputMode
from config.root import AppSettings
from domain.models.scenarios import DesignScenario
from domain.scenario_extraction import DocumentScenarioResult
from infrastructure import cli
from infrastructure.visualisation.plantuml import DiagramImageFormat

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
    monkeypatch.setattr(cli, "load_app_settings", lambda: settings)
    return settings


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
    monkeypatch.setattr(DocumentScenarioService, "extract_file", lambda *_args: result)
    options: dict[str, object] = {}

    def run(scenario: DesignScenario, directory: Path, _writer: object) -> int:
        assert scenario == result.scenario
        directory.mkdir()
        (directory / "orders_c4.json").write_text("{}", encoding="utf-8")
        reporter = options["pipeline_reporter"]
        assert isinstance(reporter, cli.RunReporter)
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

    def build(**kwargs: object) -> SimpleNamespace:
        options.update(kwargs)
        return SimpleNamespace(runner=SimpleNamespace(run=run), writer=object())

    monkeypatch.setattr(cli, "build_pipeline", build)
    code = cli.main(
        [
            "generate",
            "--brd",
            "brd.md",
            "--out",
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
    assert options["settings"] is configured
    assert configured.service_profiles is not None
    assert options["diagram_server"] == "http://localhost:8080"
    assert options["image_format"] is DiagramImageFormat.SVG
    assert options["render_diagrams"] is True
    evidence = json.loads((out / "requirements.evidence.json").read_text("utf-8"))
    assert evidence["field_evidence"] == result.field_evidence
    scenario = yaml.safe_load((out / "scenario.yaml").read_text("utf-8"))
    assert DesignScenario.model_validate(scenario) == result.scenario
    report = json.loads((out / "run.json").read_text("utf-8"))
    assert report["exit_code"] == pipeline_code
    assert report["stages"][0]["warnings"] == ["Renderer unavailable"]
    assert any("orders_c4.json" in path for path in report["artifacts"])


def test_unverified_document_stops_before_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, configured: AppSettings
) -> None:
    _ = configured
    monkeypatch.setattr(
        DocumentScenarioService,
        "extract_file",
        lambda *_args: DocumentScenarioResult(
            scenario=None,
            field_evidence={},
            issues=[],
            is_relevant=False,
            source_name="brd.md",
        ),
    )
    out = tmp_path / "result"
    assert cli.main(["generate", "--brd", "brd.md", "--out", str(out)]) == 1
    assert (out / "requirements.evidence.json").exists()
    assert not (out / "scenario.yaml").exists()
    report = json.loads((out / "run.json").read_text("utf-8"))
    assert report["stages"] == []


def test_existing_output_is_never_overwritten(tmp_path: Path) -> None:
    sentinel = tmp_path / "scenario.yaml"
    sentinel.write_text("previous run", encoding="utf-8")
    assert cli.main(["generate", "--brd", "brd.md", "--out", str(tmp_path)]) == 2
    assert sentinel.read_text("utf-8") == "previous run"


def test_missing_document_creates_failure_report(
    tmp_path: Path, configured: AppSettings
) -> None:
    _ = configured
    out = tmp_path / "result"
    assert cli.main(["generate", "--brd", "absent.md", "--out", str(out)]) == 2
    report = json.loads((out / "run.json").read_text("utf-8"))
    assert report["status"] == "failed"
