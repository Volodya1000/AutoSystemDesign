"""Architectural regression checks for typing.Protocol declarations."""

import ast
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src"


def test_typing_protocol_names_have_protocol_suffix() -> None:
    """Structural interface names must be distinguishable from implementations."""
    incorrect: list[str] = []
    for path in SOURCE_ROOT.rglob("*.py"):
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(module):
            if not isinstance(node, ast.ClassDef):
                continue
            uses_protocol = any(
                isinstance(base, ast.Name) and base.id == "Protocol"
                for base in node.bases
            )
            if uses_protocol and not node.name.endswith("Protocol"):
                incorrect.append(f"{path.relative_to(SOURCE_ROOT)}:{node.name}")

    assert not incorrect, f"Rename typing.Protocol classes: {incorrect}"


def test_legacy_ports_module_names_are_not_reintroduced() -> None:
    """Collections of Python interface declarations use protocols modules."""
    legacy_paths = [
        str(path.relative_to(SOURCE_ROOT))
        for path in SOURCE_ROOT.rglob("*.py")
        if path.stem == "ports" or path.stem.endswith("_ports")
    ]
    assert not legacy_paths, f"Use *_protocols.py instead: {legacy_paths}"
