"""Typed diagram-server selections shared by configuration and CLI adapters."""

from __future__ import annotations

from enum import StrEnum
from urllib.parse import urlsplit


class DiagramServerPreset(StrEnum):
    """Named renderer configurations supported by the PlantUML adapter."""

    AUTO = "auto"
    PLANTUML = "plantuml"
    KROKI = "kroki"


class DiagramServerSelectionError(ValueError):
    """A renderer selection is neither a preset nor an HTTP(S) URL."""

    def __init__(self, value: str) -> None:
        super().__init__(f"Unsupported diagram server selection: {value!r}")


def diagram_server_presets() -> tuple[str, ...]:
    """Return CLI/config values directly from the typed preset model."""
    return tuple(item.value for item in DiagramServerPreset)


def diagram_server_usage() -> str:
    """Describe accepted values without maintaining a second preset list."""
    return ", ".join(diagram_server_presets()) + ", or an absolute http(s) URL"


def normalize_diagram_server(value: str) -> DiagramServerPreset | str:
    """Return a typed preset or a normalized absolute server URL."""
    selection = value.strip()
    try:
        return DiagramServerPreset(selection.lower())
    except ValueError:
        parsed = urlsplit(selection)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return selection.rstrip("/")
        raise DiagramServerSelectionError(value) from None
