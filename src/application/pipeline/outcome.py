"""Immutable result types produced by pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class StageStatus(str, Enum):
    """Overall status of one stage.

    SUCCEEDED: all required and optional artifacts were produced.
    PARTIAL:   required artifacts produced; optional artifacts (rendered
               diagrams) failed. The pipeline continues.
    FAILED:    required artifacts missing; downstream stages cannot run.
    """

    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True)
class DiagramRenderResult:
    """Result of one diagram render call.

    Never raises for expected visualization errors: they are captured as
    warnings so that a missing diagram image does not hide successfully
    generated model artifacts.
    """

    artifacts: tuple[Path, ...] = ()
    warnings: tuple[str, ...] = ()
    image_rendered: bool = False


# pylint: disable=too-many-instance-attributes
@dataclass(frozen=True)
class StageOutcome[PayloadT]:
    """Everything downstream stages, reporters, and tests inspect."""

    name: str
    status: StageStatus
    # Full wall-clock time of the stage, including artifact writes and any
    # best-effort diagram rendering.
    duration_seconds: float
    total_tokens: int
    artifacts: tuple[Path, ...] = ()
    payload: PayloadT | None = None
    message: str | None = None
    warnings: tuple[str, ...] = ()
