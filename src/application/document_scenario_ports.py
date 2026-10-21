# Copyright (c) 2026 Volodya1000
"""Ports required by the document-to-scenario application service."""

from pathlib import Path
from typing import Protocol

from domain.document_requirements import DocumentRequirements
from domain.scenario_extraction import DocumentScenarioExtraction


class DocumentRequirementsProvider(Protocol):
    """Port for obtaining requirements that have already passed evidence checks."""

    def extract_file(self, path: Path) -> DocumentRequirements:
        """Read a source document and return source-grounded requirements."""


class DocumentScenarioMapper(Protocol):
    """Port implemented by the LLM adapter that proposes evidence-bearing fields."""

    def map(self, requirements: DocumentRequirements) -> DocumentScenarioExtraction:
        """Map verified requirement claims into candidate scenario values."""
