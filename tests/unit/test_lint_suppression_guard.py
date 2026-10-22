"""Verify that suppression detection distinguishes comments from strings."""

from pathlib import Path

import pytest

from scripts.check_lint_suppressions import main

pytestmark: pytest.MarkDecorator = pytest.mark.unit


@pytest.mark.parametrize(
    "marker",
    [
        "noqa",
        "type: ignore[call-arg]",
        "pylint: disable=all",
        "nosec",
        "pragma: no cover",
        "pyright: ignore",
    ],
)
def test_guard_rejects_suppression_comments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, marker: str
) -> None:
    source: Path = tmp_path / "src"
    source.mkdir()
    (source / "example.py").write_text(f"value = 1  # {marker}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main() == 1


def test_guard_accepts_comment_examples_inside_string_literals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source: Path = tmp_path / "property_tests"
    source.mkdir()
    (source / "example.py").write_text(
        'example = "# noqa and # type: ignore"\n', encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    assert main() == 0
