"""Shared initialization for pipeline stage execution."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.pipeline.context import StageContext
    from domain.models import DesignScenario


def begin_stage_execution(context: StageContext) -> tuple[float, DesignScenario]:
    """Capture the stage start time and resolve its scenario once."""
    return time.perf_counter(), context.scenario
