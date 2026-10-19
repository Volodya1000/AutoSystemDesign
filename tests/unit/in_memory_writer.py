"""Reusable test doubles shared by unit tests."""

from pathlib import Path


class InMemoryWriter:
    """Record text writes without touching the filesystem."""

    def __init__(self) -> None:
        self.writes: list[tuple[Path, str]] = []

    def write_text(self, path: Path, content: str) -> Path:
        self.writes.append((path, content))
        return path
