"""The only thing PipelineRunner knows about: a runnable stage."""

from __future__ import annotations

import time
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from application.pipeline.context import StageContext
    from application.pipeline.outcome import StageOutcome
    from domain.models import DesignScenario


class StageId(StrEnum):
    """Stable identifiers used to connect pipeline stages and their outcomes."""

    C4 = "c4"
    PERFORMANCE_ANALYSIS = "performance_analysis"
    SEQUENCE = "sequence"
    API = "api"


class PipelineStage(Protocol):
    name: StageId
    depends_on: tuple[StageId, ...]

    def run(self, context: StageContext) -> StageOutcome[object]: ...


def begin_stage_execution(context: StageContext) -> tuple[float, DesignScenario]:
    """Capture the common stage start time and scenario."""
    return time.perf_counter(), context.scenario
