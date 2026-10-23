"""Define the simulation boundary without exposing SimPy."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.architecture_simulation.graph_execution import (
        GraphRequestTrace,
        GraphTraceWindowResult,
    )
    from domain.architecture_simulation.kernel import (
        SimulationWindow,
        SingleNodeSimulationPlan,
        SingleNodeSimulationResult,
        StochasticSingleNodePlan,
        WindowSimulationResult,
    )


class SimulationEngineProtocol(Protocol):
    """Execute deterministic and horizon-limited single-node traces."""

    def simulate(
        self, plan: SingleNodeSimulationPlan
    ) -> SingleNodeSimulationResult: ...

    def simulate_window(
        self, plan: SingleNodeSimulationPlan, window: SimulationWindow
    ) -> WindowSimulationResult: ...


class ScheduleGeneratorProtocol(Protocol):
    """Generate reproducible arrivals independently of the SimPy engine."""

    def generate(
        self,
        plan: StochasticSingleNodePlan,
        window: SimulationWindow,
        arrival_seed: int,
        service_seed: int,
    ) -> SingleNodeSimulationPlan: ...


class GraphSimulationEngineProtocol(Protocol):
    """Execute a supplied graph trace independently of a concrete event engine."""

    def simulate(
        self, trace: GraphRequestTrace, window: SimulationWindow
    ) -> GraphTraceWindowResult: ...
