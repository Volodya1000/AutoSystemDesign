from collections.abc import Set as AbstractSet
from typing import Protocol

from application.tasks import (
    ApiDesignProposal,
    ApiDesignTask,
    DesignProposal,
    DesignTask,
    SequenceInteractionProposal,
    SequenceInteractionTask,
    SequenceRoleProposal,
    SequenceRoleTask,
)
from domain.models.api import ApiDesign
from domain.models.topology import ArchitectureGraph
from domain.specifications.interfaces import ValidationResult


class ArchitectureDesignerProtocol(Protocol):
    def propose(self, task: DesignTask) -> DesignProposal: ...


class SequenceDesignerProtocol(Protocol):
    def propose_roles(self, task: SequenceRoleTask) -> SequenceRoleProposal: ...
    def propose_interaction(
        self, task: SequenceInteractionTask
    ) -> SequenceInteractionProposal: ...


class ApiDesignerProtocol(Protocol):
    def propose(self, task: ApiDesignTask) -> ApiDesignProposal: ...


class ApiDesignValidatorProtocol(Protocol):
    """Application-facing contract for semantic API design validation."""

    def validate(
        self,
        api: ApiDesign,
        graph: ArchitectureGraph,
        expected_requirement_ids: AbstractSet[str],
    ) -> ValidationResult: ...
