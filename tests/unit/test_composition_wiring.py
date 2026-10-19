"""Unit tests of the stage builders in the composition root.

These exercise the wiring without any LLM: _build_*_stage accepts an
explicit AppSettings, so no environment variables or real endpoint
are required.
"""

from pathlib import Path

import pytest
from pydantic import SecretStr

from application.pipeline.diagram_subjects import SequenceDiagramSubject
from application.pipeline.stages.api import ApiStage
from application.pipeline.stages.c4 import C4Stage
from application.pipeline.stages.sequence import SequenceStage
from config.llm import LlmSettings, StructuredOutputMode
from config.root import AppSettings
from domain.models.topology import ArchitectureGraph
from infrastructure.composition import (
    _build_api_stage,
    _build_c4_stage,
    _build_sequence_stage,
    _diagram_renderer,
    build_pipeline,
)
from infrastructure.reporting import LoggingGenerationReporter
from infrastructure.visualisation.plantuml import (
    C4ContainerDiagramBuilder,
    DiagramImageFormat,
    SequenceDiagramBuilder,
)
from infrastructure.visualisation.plantuml.renderers import PlantUmlDiagramRenderer

pytestmark = pytest.mark.unit


def _settings() -> AppSettings:
    return AppSettings(
        base_url="http://localhost:1234/v1",
        api_key=SecretStr("fake"),
        llm=LlmSettings(
            model="lm_studio/fake",
            temperature=0.0,
            max_tokens=64,
            timeout_seconds=5.0,
            structured_output_mode=StructuredOutputMode.PROMPT,
        ),
    )


def test_build_c4_stage_without_renderer() -> None:
    stage = _build_c4_stage(
        _settings(), renderer=None, reporter=LoggingGenerationReporter()
    )
    assert isinstance(stage, C4Stage)
    assert stage.name == "c4"
    assert not stage.depends_on


def test_build_sequence_stage_depends_on_c4() -> None:
    stage = _build_sequence_stage(
        _settings(), renderer=None, reporter=LoggingGenerationReporter()
    )
    assert isinstance(stage, SequenceStage)
    assert stage.name == "sequence"
    assert stage.depends_on == ("c4",)


def test_build_api_stage_depends_on_c4_and_sequence() -> None:
    stage = _build_api_stage(_settings(), reporter=LoggingGenerationReporter())
    assert isinstance(stage, ApiStage)
    assert stage.name == "api"
    assert stage.depends_on == ("c4", "sequence")


def test_build_pipeline_reuses_provided_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_reloaded() -> AppSettings:
        pytest.fail("build_pipeline reloaded application settings")

    monkeypatch.setattr(
        "infrastructure.composition.load_app_settings", fail_if_reloaded
    )

    wiring = build_pipeline(
        settings=_settings(),
        diagram_server="kroki",
        image_format=DiagramImageFormat.PNG,
        render_diagrams=False,
    )

    assert wiring.runner is not None
    assert wiring.writer is not None


def test_diagram_renderer_keeps_concrete_subject_types() -> None:
    c4_renderer = _diagram_renderer(
        C4ContainerDiagramBuilder(),
        server="kroki",
        image_format=DiagramImageFormat.SVG,
        enabled=True,
    )
    sequence_renderer = _diagram_renderer(
        SequenceDiagramBuilder(),
        server="kroki",
        image_format=DiagramImageFormat.SVG,
        enabled=True,
    )

    # The assignments intentionally pin the generic types expected by stages.
    c4_typed_renderer: PlantUmlDiagramRenderer[ArchitectureGraph] | None = c4_renderer
    sequence_typed_renderer: PlantUmlDiagramRenderer[SequenceDiagramSubject] | None = (
        sequence_renderer
    )
    assert c4_typed_renderer is not None
    assert sequence_typed_renderer is not None


def test_mypy_rejects_default_builder_for_non_architecture_subject(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default C4 builder must not type-check for a sequence subject."""
    from mypy import api

    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("MYPYPATH", str(repo_root / "src"))
    sample = tmp_path / "invalid_diagram_service.py"
    sample.write_text(
        "from application.pipeline.diagram_subjects import SequenceDiagramSubject\n"
        "from infrastructure.visualisation.plantuml.diagram_service import DiagramService\n"
        "DiagramService[SequenceDiagramSubject]()\n",
        encoding="utf-8",
    )

    stdout, stderr, exit_status = api.run(
        [
            "--config-file",
            str(repo_root / "pyproject.toml"),
            "--no-incremental",
            str(sample),
        ]
    )
    diagnostics = stdout + stderr

    assert exit_status != 0, diagnostics
    assert "No overload variant" in diagnostics, diagnostics
