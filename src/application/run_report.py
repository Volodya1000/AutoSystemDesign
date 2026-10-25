"""Typed contract for a complete document-generation run."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.pipeline.outcome import StageStatus
    from application.pipeline.stage import StageId


class RunStatus(StrEnum):
    """Overall document-generation status."""

    COMPLETED = "completed"
    FAILED = "failed"


class PerformanceInputMode(StrEnum):
    """Identify where performance parameters came from."""

    GENERATED_C4 = "llm_generated_c4_parameters"
    EXPLICIT_PROFILES = "explicit_service_profiles"


@dataclass(frozen=True)
class RunStageReport:
    """Serializable summary of one pipeline stage."""

    name: StageId
    status: StageStatus
    duration_seconds: float
    total_tokens: int
    warnings: list[str]
    message: str | None


@dataclass(frozen=True)
class DocumentRunReport:
    """Machine-readable summary written beside generated artifacts."""

    source: str
    exit_code: int
    status: RunStatus
    performance_input_mode: PerformanceInputMode
    artifacts: list[str]
    stages: list[RunStageReport]
    error: str | None
