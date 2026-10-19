"""Typed result models for sequence artifact processing."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SequenceArtifactResult:
    """Artifacts produced for one interaction plus best-effort render warnings."""

    artifacts: tuple[Path, ...]
    warnings: tuple[str, ...] = ()
