"""Ensure each client boundary belongs to a single business role."""

from __future__ import annotations

from domain.exceptions.sequence_errors import SharedClientLifelineError
from domain.models.enums import NodeType
from domain.models.sequence import ComponentLifeline, InteractionScenario, UserLifeline
from domain.specifications.interfaces import ValidationResult

from .helpers import iter_message_steps

if TYPE_CHECKING:
    from domain.models.roles import ProjectRolesCatalog
    from domain.models.topology import ArchitectureGraph

from typing import TYPE_CHECKING


class ClientOwnershipValidator:
    """Reject client lifelines used by multiple distinct business roles."""

    def validate_scenario(
        self,
        scenario: InteractionScenario,
        catalog: ProjectRolesCatalog,
        graph: ArchitectureGraph,
        expected_requirement_id: str,
    ) -> ValidationResult:
        _ = catalog, expected_requirement_id
        node_type_by_id = {node.identifier: node.node_type for node in graph.nodes}
        client_ids = {
            lifeline.lifeline_id
            for lifeline in scenario.lifelines
            if isinstance(lifeline, ComponentLifeline)
            and node_type_by_id.get(lifeline.architecture_node_id) is NodeType.CLIENT
        }
        if not client_ids:
            return ValidationResult(errors=[])

        role_by_lifeline_id = {
            lifeline.lifeline_id: lifeline.business_role_id
            for lifeline in scenario.lifelines
            if isinstance(lifeline, UserLifeline)
        }
        client_roles: dict[str, set[str]] = {client_id: set() for client_id in client_ids}
        for message in iter_message_steps(scenario.steps):
            for client_id, user_id in (
                (message.from_lifeline, message.to_lifeline),
                (message.to_lifeline, message.from_lifeline),
            ):
                role = role_by_lifeline_id.get(user_id)
                if client_id in client_ids and role is not None:
                    client_roles[client_id].add(role)

        errors = [
            SharedClientLifelineError(
                client_lifeline_id=client_id,
                business_role_ids=sorted(roles),
            )
            for client_id, roles in client_roles.items()
            if len(roles) > 1
        ]
        return ValidationResult(errors=errors)
