# Copyright (c) 2026 Volodya1000
"""The only thing PipelineRunner knows about: a runnable stage."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from application.pipeline.context import StageContext
    from application.pipeline.outcome import StageOutcome


class PipelineStage(Protocol):
    name: str
    depends_on: tuple[str, ...]

    def run(self, context: StageContext) -> StageOutcome[object]: ...
