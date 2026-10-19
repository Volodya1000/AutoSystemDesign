"""Sequence-diagram validators.

The module provides narrow, single-responsibility validators:

* ``SequenceIntegrityValidator`` checks referential integrity: no
  duplicate role ids in the catalog, every ``UserLifeline`` references a
  known ``business_role_id``, every ``ComponentLifeline`` references a
  known C4 node, and the scenario implements the expected requirement.
* ``ClientOwnershipValidator`` enforces that a client boundary component
  is owned by exactly one business role: two different actors must not
  share the same client component.
* ``DeliveryModeValidator`` requires fire-and-forget messages
  (``message_kind`` is ``event`` or ``notification``) to be marked
  ``delivery_mode='async'`` so the renderer draws dashed arrows.

``SequenceGenerationService`` accepts collections of
``SequenceCatalogValidator`` and ``SequenceScenarioValidator``
instances, so adding a new rule only requires a new class and one
wiring line in ``infrastructure.composition``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from domain.exceptions.sequence_errors import (
    AsyncDeliveryModeError,
    SequenceIntegrityError,
    SharedClientLifelineError,
)
from domain.models.ast_steps import (
    AltStep,
    LoopStep,
    MessageStep,
    OptStep,
    ScenarioStep,
)
from domain.models.enums import NodeType
from domain.models.sequence import ComponentLifeline, InteractionScenario, UserLifeline
from domain.specifications.interfaces import ValidationResult

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from domain.exceptions.architecture_errors import ArchitectureValidationError
    from domain.models.roles import ProjectRolesCatalog
    from domain.models.topology import ArchitectureGraph

_ASYNC_MESSAGE_KINDS: frozenset[str] = frozenset({"event", "notification"})


# ------------------------------------------------------------------ protocols


class SequenceCatalogValidator(Protocol):
    """Validates a ``ProjectRolesCatalog``."""

    def validate_catalog(self, catalog: ProjectRolesCatalog) -> ValidationResult: ...


class SequenceScenarioValidator(Protocol):
    """Validates an ``InteractionScenario`` against its context."""

    def validate_scenario(
        self,
        scenario: InteractionScenario,
        catalog: ProjectRolesCatalog,
        graph: ArchitectureGraph,
        expected_requirement_id: str,
    ) -> ValidationResult: ...


# -------------------------------------------------------------------- helpers


def _iter_message_steps(steps: Sequence[ScenarioStep]) -> Iterator[MessageStep]:
    """Yields every ``MessageStep``, recursively descending into blocks."""
    for step in steps:
        if isinstance(step, MessageStep):
            yield step
        elif isinstance(step, AltStep):
            for branch in step.branches:
                yield from _iter_message_steps(branch.steps)
        elif isinstance(step, (OptStep, LoopStep)):
            yield from _iter_message_steps(step.steps)


# ----------------------------------------------------------------- validators


class SequenceIntegrityValidator:
    """Referential integrity across catalog, graph and scenario.

    Implements both ``SequenceCatalogValidator`` and
    ``SequenceScenarioValidator`` because referential checks for the
    catalog and for the scenario belong to the same concern: cross-
    referencing between the payload and its context.
    """

    def validate_catalog(self, catalog: ProjectRolesCatalog) -> ValidationResult:
        errors: list[ArchitectureValidationError] = []
        seen_roles: set[str] = set()
        for role in catalog.roles:
            if role.role_id in seen_roles:
                errors.append(
                    SequenceIntegrityError(f"Duplicate role_id: {role.role_id}")
                )
            seen_roles.add(role.role_id)
        return ValidationResult(errors=errors)

    def validate_scenario(
        self,
        scenario: InteractionScenario,
        catalog: ProjectRolesCatalog,
        graph: ArchitectureGraph,
        expected_requirement_id: str,
    ) -> ValidationResult:
        errors: list[ArchitectureValidationError] = []

        if scenario.requirement_identifier != expected_requirement_id:
            errors.append(
                SequenceIntegrityError(
                    f"Scenario claims to implement '{scenario.requirement_identifier}', "
                    f"but was requested for '{expected_requirement_id}'."
                )
            )

        valid_role_ids = {role.role_id for role in catalog.roles}
        valid_node_ids = {node.identifier for node in graph.nodes}

        for lifeline in scenario.lifelines:
            if isinstance(lifeline, UserLifeline):
                if lifeline.business_role_id not in valid_role_ids:
                    errors.append(
                        SequenceIntegrityError(
                            f"UserLifeline '{lifeline.lifeline_id}' references unknown "
                            f"business_role_id '{lifeline.business_role_id}'."
                        )
                    )
            elif (
                isinstance(lifeline, ComponentLifeline)
                and lifeline.architecture_node_id not in valid_node_ids
            ):
                errors.append(
                    SequenceIntegrityError(
                        f"ComponentLifeline '{lifeline.lifeline_id}' references unknown "
                        f"architecture_node_id '{lifeline.architecture_node_id}'. "
                        "Must be a valid C4 node."
                    )
                )

        return ValidationResult(errors=errors)


class ClientOwnershipValidator:
    """A client boundary component must be owned by exactly one business role.

    A C4 ``client`` node is a personal entry point (mobile app, browser
    tab). Two different actors must not interact through the same client
    component: if ``buyer`` and ``admin`` both use ``social_client``, the
    diagram cannot tell whose requests are whose, and the LLM has
    effectively merged two separate front-ends into one.

    The check only looks at messages: a declared but completely unused
    client is the "unused lifeline" problem and is rejected by the
    ``InteractionScenario`` model validator.
    """

    def validate_scenario(
        self,
        scenario: InteractionScenario,
        catalog: ProjectRolesCatalog,
        graph: ArchitectureGraph,
        expected_requirement_id: str,
    ) -> ValidationResult:
        # catalog and expected_requirement_id are not used by this rule.
        _ = catalog, expected_requirement_id

        node_type_by_id: dict[str, NodeType] = {
            node.identifier: node.node_type for node in graph.nodes
        }
        client_lifeline_ids: set[str] = {
            lifeline.lifeline_id
            for lifeline in scenario.lifelines
            if isinstance(lifeline, ComponentLifeline)
            and node_type_by_id.get(lifeline.architecture_node_id) is NodeType.CLIENT
        }
        if not client_lifeline_ids:
            return ValidationResult(errors=[])

        role_by_lifeline_id: dict[str, str] = {
            lifeline.lifeline_id: lifeline.business_role_id
            for lifeline in scenario.lifelines
            if isinstance(lifeline, UserLifeline)
        }

        client_roles: dict[str, set[str]] = {
            client_id: set() for client_id in client_lifeline_ids
        }
        for message in _iter_message_steps(scenario.steps):
            for client_id, user_id in (
                (message.from_lifeline, message.to_lifeline),
                (message.to_lifeline, message.from_lifeline),
            ):
                if client_id not in client_lifeline_ids:
                    continue
                role: str | None = role_by_lifeline_id.get(user_id)
                if role is not None:
                    client_roles[client_id].add(role)

        errors: list[ArchitectureValidationError] = [
            SharedClientLifelineError(
                client_lifeline_id=client_id,
                business_role_ids=sorted(roles),
            )
            for client_id, roles in client_roles.items()
            if len(roles) > 1
        ]
        return ValidationResult(errors=errors)


class DeliveryModeValidator:
    """``event`` and ``notification`` messages must be asynchronous."""

    def validate_scenario(
        self,
        scenario: InteractionScenario,
        catalog: ProjectRolesCatalog,
        graph: ArchitectureGraph,
        expected_requirement_id: str,
    ) -> ValidationResult:
        # catalog, graph and expected_requirement_id are not used by this
        # rule: it only inspects the message AST.
        _ = catalog, graph, expected_requirement_id

        errors: list[ArchitectureValidationError] = [
            AsyncDeliveryModeError(
                action_name=message.action_name,
                message_kind=message.message_kind,
            )
            for message in _iter_message_steps(scenario.steps)
            if message.message_kind in _ASYNC_MESSAGE_KINDS
            and message.delivery_mode != "async"
        ]
        return ValidationResult(errors=errors)
