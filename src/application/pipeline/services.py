"""Application-level service contracts used by pipeline stages."""

from __future__ import annotations

from typing import Protocol

from application.results import (
    DesignGenerationResult,
    SequenceGenerationResult,
)
from domain.models import DesignScenario
from domain.models.topology import ArchitectureGraph


class DesignGenerator(Protocol):
    def generate(self, scenario: DesignScenario) -> DesignGenerationResult: ...


class SequenceGenerator(Protocol):
    def generate(
        self,
        scenario: DesignScenario,
        graph: ArchitectureGraph,
    ) -> SequenceGenerationResult: ...
