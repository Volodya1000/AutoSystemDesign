"""Run a supplied graph with deterministic baseline and peak traffic."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from application.architecture_simulation.graph_mapper import (
    ArchitectureSimulationPlanMapper,
)
from application.architecture_simulation.trace_report import GraphTraceReportBuilder
from domain.architecture_simulation.graph_execution import GraphRequestTrace
from domain.architecture_simulation.kernel import SimulationWindow
from domain.architecture_simulation.offline import (
    OfflineSimulationInput,
    OfflineSimulationResult,
    WorkloadObservation,
)
from domain.architecture_simulation.report import SimulationWorkload

if TYPE_CHECKING:
    from application.architecture_simulation.protocols import (
        GraphSimulationEngineProtocol,
    )
    from domain.architecture_simulation.graph_plan import GraphSimulationPlan


class OfflineSimulationConfigurationError(ValueError):
    """The demonstration cannot truthfully execute the supplied configuration."""


class OfflineSimulationRunner:
    """Compose graph mapping, an event engine and canonical report construction."""

    def __init__(self, engine: GraphSimulationEngineProtocol) -> None:
        self._engine: GraphSimulationEngineProtocol = engine

    def run(self, inputs: OfflineSimulationInput) -> OfflineSimulationResult:
        """Execute both traffic levels without an LLM, clock or network client."""
        if inputs.configuration.replications != 1 or (
            inputs.configuration.warmup_seconds != 0
        ):
            message: str = "The offline demo requires one replication and zero warmup"
            raise OfflineSimulationConfigurationError(message)
        plan: GraphSimulationPlan = ArchitectureSimulationPlanMapper().map(
            inputs.graph, inputs.scenario
        )
        window: SimulationWindow = SimulationWindow(
            warmup_seconds=0,
            measurement_seconds=inputs.configuration.measurement_seconds,
            max_events=inputs.configuration.max_events_per_replication,
        )
        observations: list[WorkloadObservation] = []
        workload: SimulationWorkload
        rate: float
        for workload, rate in (
            (SimulationWorkload.BASELINE, plan.baseline_requests_per_second),
            (SimulationWorkload.PEAK, plan.peak_requests_per_second),
        ):
            count: int = math.ceil(rate * window.measurement_seconds)
            if count > window.max_events:
                message = "Request schedule exceeds the configured event budget"
                raise OfflineSimulationConfigurationError(message)
            arrivals: list[float] = [
                index / rate
                for index in range(count)
                if index / rate < window.horizon_seconds
            ]
            observations.append(
                WorkloadObservation(
                    workload_id=workload,
                    offered_requests_per_second=rate,
                    result=self._engine.simulate(
                        GraphRequestTrace(
                            plan=plan,
                            arrival_times_seconds=arrivals,
                            seed=inputs.configuration.base_seed,
                        ),
                        window,
                    ),
                )
            )
        return OfflineSimulationResult(
            inputs=inputs,
            plan=plan,
            observations=observations,
            report=GraphTraceReportBuilder().build(inputs, observations),
        )
