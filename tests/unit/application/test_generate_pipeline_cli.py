"""Verify CLI status mapping without spawning a process or calling an LLM."""

from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from application.pipeline.outcome import StageOutcome, StageStatus
from application.pipeline.result import PipelineRunResult
from application.pipeline.stage import StageId
from infrastructure.visualisation.plantuml import DiagramImageFormat
from scripts import generate_pipeline
from scripts.generate_pipeline import PipelineExitCode

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("status", "expected_exit_code"),
    [
        (StageStatus.SUCCEEDED, PipelineExitCode.SUCCESS),
        (StageStatus.PARTIAL, PipelineExitCode.SUCCESS),
        (StageStatus.FAILED, PipelineExitCode.STAGE_FAILURE),
    ],
)
def test_cli_converts_pipeline_result_to_process_code(
    status: StageStatus,
    expected_exit_code: PipelineExitCode,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    outcome: StageOutcome[object] = StageOutcome[object](
        name=StageId.C4,
        status=status,
        duration_seconds=0.0,
        total_tokens=0,
    )
    runner: MagicMock = MagicMock()
    runner.run.return_value = PipelineRunResult((outcome,))
    monkeypatch.setattr(
        generate_pipeline,
        "_parse_args",
        MagicMock(
            return_value=Namespace(
                verbose=False, no_diagram=True, scenario="fixture.yaml"
            )
        ),
    )
    monkeypatch.setattr(generate_pipeline, "configure_logging", MagicMock())
    monkeypatch.setattr(
        generate_pipeline, "load_app_settings", MagicMock(return_value=MagicMock())
    )
    monkeypatch.setattr(
        generate_pipeline, "_load_scenario", MagicMock(return_value=MagicMock())
    )
    monkeypatch.setattr(
        generate_pipeline,
        "_resolve_visualisation",
        MagicMock(return_value=(tmp_path, "kroki", DiagramImageFormat.PNG)),
    )
    monkeypatch.setattr(generate_pipeline, "log_header", MagicMock())
    monkeypatch.setattr(
        generate_pipeline,
        "build_pipeline",
        MagicMock(return_value=SimpleNamespace(runner=runner, writer=MagicMock())),
    )

    assert generate_pipeline.main() == expected_exit_code
    runner.run.assert_called_once()


def test_cli_preserves_configuration_error_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        generate_pipeline,
        "_parse_args",
        MagicMock(return_value=Namespace(verbose=False)),
    )
    monkeypatch.setattr(generate_pipeline, "configure_logging", MagicMock())
    monkeypatch.setattr(
        generate_pipeline, "load_app_settings", MagicMock(side_effect=ValueError)
    )

    assert generate_pipeline.main() is PipelineExitCode.INPUT_OR_CONNECTION_ERROR


@pytest.mark.parametrize(
    ("code", "numeric_value"),
    [
        (PipelineExitCode.SUCCESS, 0),
        (PipelineExitCode.STAGE_FAILURE, 1),
        (PipelineExitCode.INPUT_OR_CONNECTION_ERROR, 2),
    ],
)
def test_exit_codes_preserve_public_numeric_contract(
    code: PipelineExitCode,
    numeric_value: int,
) -> None:
    assert int(code) == numeric_value
