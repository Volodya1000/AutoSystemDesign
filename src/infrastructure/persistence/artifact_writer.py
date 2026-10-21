"""Filesystem implementation of application.pipeline.protocols.ArtifactWriterProtocol."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger("pipeline.artifact")


class FileSystemArtifactWriter:
    def __init__(self, *, log_writes: bool = True) -> None:
        self._log_writes: bool = log_writes

    def write_text(self, path: Path, content: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if self._log_writes:
            _logger.info("Artifact written: %s", path)
        return path

    def write_bytes(self, path: Path, content: bytes) -> Path:
        """Persist a binary artifact without applying text encoding."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        if self._log_writes:
            _logger.info("Artifact written: %s", path)
        return path
