"""Static regression tests for diagram source builder subject types."""

import sys
from pathlib import Path

import pytest
from mypy import api as mypy_api

pytestmark = pytest.mark.unit


def test_mypy_rejects_builder_for_the_wrong_subject_type(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A C4 builder cannot satisfy the source-builder protocol for sequences."""
    repo_root = Path(__file__).resolve().parents[3]
    monkeypatch.setenv("MYPYPATH", str(repo_root / "src"))
    sample = tmp_path / "invalid_diagram_builder.py"
    sample.write_text(
        "from application.pipeline.diagram_subjects import SequenceDiagramSubject\n"
        "from infrastructure.visualisation.plantuml.c4_container_builder "
        "import C4ContainerDiagramBuilder\n"
        "from infrastructure.visualisation.plantuml.ports import DiagramSourceBuilder\n"
        "builder: DiagramSourceBuilder[SequenceDiagramSubject] = "
        "C4ContainerDiagramBuilder()\n",
        encoding="utf-8",
    )

    stdout, stderr, exit_status = mypy_api.run(
        [
            "--config-file",
            str(repo_root / "pyproject.toml"),
            "--no-incremental",
            str(sample),
        ]
    )
    diagnostics = stdout + stderr

    assert exit_status != 0, diagnostics
    assert "Incompatible types in assignment" in diagnostics, diagnostics
