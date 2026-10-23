"""Define reproducible offline inputs and raw event evidence."""

from pydantic import Field

from domain.architecture_simulation.configuration import SimulationConfiguration
from domain.architecture_simulation.graph_execution import GraphTraceWindowResult
from domain.architecture_simulation.graph_plan import GraphSimulationPlan
from domain.architecture_simulation.report import (
    SimulationDataModel,
    SimulationReport,
    SimulationWorkload,
)
from domain.models.scenarios import DesignScenario
from domain.models.topology import ArchitectureGraph


class OfflineSimulationInput(SimulationDataModel):
    """Accept an existing C4 graph without invoking architecture generation."""

    graph: ArchitectureGraph
    scenario: DesignScenario
    configuration: SimulationConfiguration


class WorkloadObservation(SimulationDataModel):
    """Keep a workload label alongside the engine's unrounded observations."""

    workload_id: SimulationWorkload
    offered_requests_per_second: float = Field(gt=0)
    result: GraphTraceWindowResult


class OfflineSimulationResult(SimulationDataModel):
    """Retain inputs, raw traces and the canonical report for reproduction."""

    inputs: OfflineSimulationInput
    plan: GraphSimulationPlan
    observations: list[WorkloadObservation]
    report: SimulationReport
