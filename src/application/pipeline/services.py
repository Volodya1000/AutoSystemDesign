# Copyright (c) 2026 Volodya1000
"""Application-level service contracts used by pipeline stages."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping

    from application.results import (
        ApiGenerationResult,
        DesignGenerationResult,
        SequenceGenerationResult,
    )
    from domain.models import DesignScenario
    from domain.models.sequence import InteractionScenario
    from domain.models.topology import ArchitectureGraph


class DesignGenerator(Protocol):
    def generate(self, scenario: DesignScenario) -> DesignGenerationResult: ...


class SequenceGenerator(Protocol):
    def generate(
        self,
        scenario: DesignScenario,
        graph: ArchitectureGraph,
    ) -> SequenceGenerationResult: ...


class ApiGenerator(Protocol):
    def generate(
        self,
        scenario: DesignScenario,
        graph: ArchitectureGraph,
        sequences: Mapping[str, InteractionScenario],
    ) -> ApiGenerationResult: ...
