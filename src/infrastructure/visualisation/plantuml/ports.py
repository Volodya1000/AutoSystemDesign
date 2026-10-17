from typing import Any, Protocol


class DiagramSourceBuilder(Protocol):
    def build(self, subject: Any, title: str | None = None) -> str: ...
