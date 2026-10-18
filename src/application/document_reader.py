"""Application port for adapters that extract text from source documents."""

from pathlib import Path
from typing import Protocol


class DocumentReader(Protocol):
    """Strategy contract implemented by format-specific infrastructure adapters."""

    def read_text(self, path: Path) -> str:
        """Return readable text while preserving source meaning."""
