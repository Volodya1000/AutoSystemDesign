import json
import logging
from pathlib import Path

import pytest
import yaml

from domain.document_requirements import RequirementIssue, RequirementIssueKind
from domain.models.scenarios import DesignScenario
from domain.scenario_extraction import DocumentScenarioResult
from scripts import extract_document_scenario as cli


def _dummy_factory(*_args: object, **_kwargs: object) -> object:
    """Return an inert object for dependencies unused by the CLI test."""
    return object()


@pytest.mark.unit
def test_main_writes_pipeline_yaml_and_evidence_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    document = tmp_path / "spec.md"
    document.write_text("The service supports login.", encoding="utf-8")
    output = tmp_path / "nested" / "scenario.yaml"
    evidence_output = tmp_path / "nested" / "scenario.evidence.json"
    expected = DocumentScenarioResult(
        scenario=DesignScenario(
            identifier="spec",
            description="The service supports login.",
        ),
        field_evidence={"description": "The service supports login."},
        issues=[
            RequirementIssue(
                kind=RequirementIssueKind.MISSING,
                field="workload.read_ratio",
                description="No ratio in source.",
            )
        ],
        is_relevant=True,
        source_name=document.name,
    )
    pipeline_calls: list[list[str]] = []

    class FakeService:
        def __init__(self, requirements_service: object, mapper: object) -> None:
            pass

        def extract_file(self, path: Path) -> DocumentScenarioResult:
            assert path == document
            return expected

    class FakeProcess:
        async def wait(self) -> int:
            return 0

    async def fake_create_subprocess_exec(*command: str) -> FakeProcess:
        pipeline_calls.append(list(command))
        return FakeProcess()

    monkeypatch.setattr(cli, "load_app_settings", object)
    monkeypatch.setattr(cli, "LlmDocumentRequirementExtractor", _dummy_factory)
    monkeypatch.setattr(cli, "DocumentRequirementsService", _dummy_factory)
    monkeypatch.setattr(cli, "LlmDocumentScenarioMapper", _dummy_factory)
    monkeypatch.setattr(cli, "DocumentScenarioService", FakeService)
    monkeypatch.setattr(
        cli.asyncio, "create_subprocess_exec", fake_create_subprocess_exec
    )

    exit_code = cli.main(
        [
            "--document",
            str(document),
            "--output",
            str(output),
            "--evidence-output",
            str(evidence_output),
            "--run-pipeline",
            "--no-diagram",
            "--pipeline-out-dir",
            str(tmp_path / "pipeline-output"),
        ]
    )

    assert exit_code == 0
    assert "Generated scenario:" in caplog.text
    assert "Evidence manifest:" in caplog.text
    scenario_payload = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert scenario_payload["identifier"] == "spec"
    assert scenario_payload["description"] == "The service supports login."
    evidence_payload = json.loads(evidence_output.read_text(encoding="utf-8"))
    assert evidence_payload["field_evidence"]["description"] == (
        "The service supports login."
    )
    assert evidence_payload["scenario_created"]
    assert len(pipeline_calls) == 1
    assert any(item.endswith("generate_pipeline.py") for item in pipeline_calls[0])
    assert "--scenario" in pipeline_calls[0]
    assert str(output) in pipeline_calls[0]
    assert "--no-diagram" in pipeline_calls[0]
    assert "--out-dir" in pipeline_calls[0]


@pytest.mark.unit
def test_main_does_not_write_scenario_without_validated_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    document = tmp_path / "spec.md"
    document.write_text("Nothing testable.", encoding="utf-8")
    output = tmp_path / "scenario.yaml"
    evidence_output = tmp_path / "scenario.evidence.json"
    result = DocumentScenarioResult(
        scenario=None,
        field_evidence={},
        issues=[],
        is_relevant=False,
        source_name=document.name,
    )

    class FakeService:
        def __init__(self, requirements_service: object, mapper: object) -> None:
            pass

        def extract_file(self, _path: Path) -> DocumentScenarioResult:
            return result

    monkeypatch.setattr(cli, "load_app_settings", object)
    monkeypatch.setattr(cli, "LlmDocumentRequirementExtractor", _dummy_factory)
    monkeypatch.setattr(cli, "DocumentRequirementsService", _dummy_factory)
    monkeypatch.setattr(cli, "LlmDocumentScenarioMapper", _dummy_factory)
    monkeypatch.setattr(cli, "DocumentScenarioService", FakeService)

    exit_code = cli.main(
        [
            "--document",
            str(document),
            "--output",
            str(output),
            "--evidence-output",
            str(evidence_output),
        ]
    )

    assert exit_code == 1
    assert "No pipeline scenario was written" in caplog.text
    assert not output.exists()
    assert evidence_output.exists()
