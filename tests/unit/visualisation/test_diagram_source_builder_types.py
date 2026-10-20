"""Static regression tests for diagram source builder subject types."""

import subprocess
import sys
from pathlib import Path

import pytest

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

    # Use the current interpreter with a generated test file and explicit argv.
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "mypy",
            "--config-file",
            str(repo_root / "pyproject.toml"),
            "--no-incremental",
            str(sample),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    diagnostics = result.stdout + result.stderr

    assert result.returncode != 0, diagnostics
    assert "Incompatible types in assignment" in diagnostics, diagnostics
