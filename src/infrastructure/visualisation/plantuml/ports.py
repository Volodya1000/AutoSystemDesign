"""Ports for diagram source construction."""

from typing import Protocol


class DiagramSourceBuilder[SubjectT](Protocol):
    """Builds diagram source from the matching typed input subject."""

    def build(self, subject: SubjectT, title: str | None = None) -> str: ...
