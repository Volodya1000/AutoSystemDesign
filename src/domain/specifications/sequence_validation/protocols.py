# Copyright (c) 2026 Volodya1000
"""Protocols for sequence validation rules."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.models.roles import ProjectRolesCatalog
    from domain.models.sequence import InteractionScenario
    from domain.models.topology import ArchitectureGraph
    from domain.specifications.interfaces import ValidationResult


class SequenceCatalogValidator(Protocol):
    """Validates a roles catalog."""

    def validate_catalog(self, catalog: ProjectRolesCatalog) -> ValidationResult: ...


class SequenceScenarioValidator(Protocol):
    """Validates a scenario against its context."""

    def validate_scenario(
        self,
        scenario: InteractionScenario,
        catalog: ProjectRolesCatalog,
        graph: ArchitectureGraph,
        expected_requirement_id: str,
    ) -> ValidationResult: ...
