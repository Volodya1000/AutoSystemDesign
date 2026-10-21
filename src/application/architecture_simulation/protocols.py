"""Declare simulation engine capabilities without importing SimPy."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.architecture_simulation.kernel import (
        SingleNodeSimulationPlan,
        SingleNodeSimulationResult,
    )


class SimulationEngineProtocol(Protocol):
    """Execute a reproducible trace for one service node."""

    def simulate(
        self, plan: SingleNodeSimulationPlan
    ) -> SingleNodeSimulationResult: ...
