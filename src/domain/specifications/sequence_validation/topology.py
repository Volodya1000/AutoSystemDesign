"""Check component messages against directed C4 links and pending calls."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from domain.exceptions.sequence_errors import SequenceTopologyError
from domain.models.ast_steps import AltStep, LoopStep, MessageStep, OptStep
from domain.models.sequence import ComponentLifeline
from domain.specifications.interfaces import ValidationResult

if TYPE_CHECKING:
    from collections.abc import Sequence

    from domain.models.ast_steps import ScenarioStep
    from domain.models.roles import ProjectRolesCatalog
    from domain.models.sequence import InteractionScenario
    from domain.models.topology import ArchitectureGraph

type PendingCalls = Counter[tuple[str, str]]


class SequenceTopologyValidator:
    """Reject messages that invent links or reverse unpaired requests."""

    def validate_scenario(
        self,
        scenario: InteractionScenario,
        catalog: ProjectRolesCatalog,
        graph: ArchitectureGraph,
        expected_requirement_id: str,
    ) -> ValidationResult:
        _ = catalog, expected_requirement_id
        check: _TopologyCheck = _TopologyCheck(scenario, graph)
        check.validate_steps(scenario.steps, Counter())
        return ValidationResult(errors=list(check.errors))


class _TopologyCheck:
    """Track outstanding synchronous calls independently on each branch."""

    def __init__(self, scenario: InteractionScenario, graph: ArchitectureGraph) -> None:
        self._components: dict[str, str] = {
            lifeline.lifeline_id: lifeline.architecture_node_id
            for lifeline in scenario.lifelines
            if isinstance(lifeline, ComponentLifeline)
        }
        self._links: set[tuple[str, str, bool]] = {
            (
                edge.source_identifier,
                edge.target_identifier,
                edge.protocol.is_asynchronous,
            )
            for edge in graph.edges
        }
        self.errors: list[SequenceTopologyError] = []

    def validate_steps(
        self, steps: Sequence[ScenarioStep], pending: PendingCalls
    ) -> PendingCalls:
        """Return calls guaranteed to remain outstanding after these steps."""
        state: PendingCalls = pending.copy()
        for step in steps:
            if isinstance(step, MessageStep):
                self._validate_message(step, state)
            elif isinstance(step, AltStep):
                outcomes: list[PendingCalls] = [
                    self.validate_steps(branch.steps, state) for branch in step.branches
                ]
                if step.branches[-1].condition is not None:
                    outcomes.append(state)
                state = outcomes[0]
                for outcome in outcomes[1:]:
                    state &= outcome
            elif isinstance(step, (LoopStep, OptStep)):
                state &= self.validate_steps(step.steps, state)
        return state

    def _validate_message(self, message: MessageStep, pending: PendingCalls) -> None:
        source: str | None = self._components.get(message.from_lifeline)
        target: str | None = self._components.get(message.to_lifeline)
        if source is None or target is None or source == target:
            return
        if message.message_kind == "response":
            self._validate_response(message, pending, source, target)
            return
        asynchronous: bool = message.delivery_mode == "async"
        if (
            message.delivery_mode is None
            or (source, target, asynchronous) not in self._links
        ):
            self.errors.append(
                SequenceTopologyError(
                    source,
                    target,
                    "No directed C4 link supports this message delivery mode. "
                    "Use an existing link and its sync/async mode.",
                )
            )
        elif message.message_kind == "request" and not asynchronous:
            pending[(message.from_lifeline, message.to_lifeline)] += 1

    def _validate_response(
        self,
        message: MessageStep,
        pending: PendingCalls,
        source: str,
        target: str,
    ) -> None:
        request: tuple[str, str] = (message.to_lifeline, message.from_lifeline)
        if message.delivery_mode != "sync" or pending[request] == 0:
            self.errors.append(
                SequenceTopologyError(
                    source,
                    target,
                    "A response requires a preceding synchronous request on "
                    "the same execution branch and the same lifelines.",
                )
            )
        else:
            pending[request] -= 1
