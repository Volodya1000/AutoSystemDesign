# Copyright (c) 2026 Volodya1000
"""Shared traversal helpers for sequence validation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.models.ast_steps import (
    AltStep,
    LoopStep,
    MessageStep,
    OptStep,
    ScenarioStep,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence


def iter_message_steps(steps: Sequence[ScenarioStep]) -> Iterator[MessageStep]:
    """Yield message steps recursively, including messages inside control blocks."""
    for step in steps:
        if isinstance(step, MessageStep):
            yield step
        elif isinstance(step, AltStep):
            for branch in step.branches:
                yield from iter_message_steps(branch.steps)
        elif isinstance(step, (OptStep, LoopStep)):
            yield from iter_message_steps(step.steps)
