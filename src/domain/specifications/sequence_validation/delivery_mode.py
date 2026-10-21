# Copyright (c) 2026 Volodya1000
"""Delivery-mode rules for sequence messages."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.exceptions.sequence_errors import AsyncDeliveryModeError
from domain.specifications.interfaces import ValidationResult

from .helpers import iter_message_steps

if TYPE_CHECKING:
    from domain.exceptions.architecture_errors import ArchitectureValidationError
    from domain.models.roles import ProjectRolesCatalog
    from domain.models.sequence import InteractionScenario
    from domain.models.topology import ArchitectureGraph

_ASYNC_MESSAGE_KINDS: frozenset[str] = frozenset({"event", "notification"})


class DeliveryModeValidator:
    """Require event and notification messages to use asynchronous delivery."""

    def validate_scenario(
        self,
        scenario: InteractionScenario,
        catalog: ProjectRolesCatalog,
        graph: ArchitectureGraph,
        expected_requirement_id: str,
    ) -> ValidationResult:
        _ = catalog, graph, expected_requirement_id
        errors: list[ArchitectureValidationError] = [
            AsyncDeliveryModeError(
                action_name=message.action_name,
                message_kind=message.message_kind,
            )
            for message in iter_message_steps(scenario.steps)
            if message.message_kind in _ASYNC_MESSAGE_KINDS
            and message.delivery_mode != "async"
        ]
        return ValidationResult(errors=errors)
