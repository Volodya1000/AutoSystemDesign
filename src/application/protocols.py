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


class ArchitectureDesigner(Protocol):
    def propose(self, task: DesignTask) -> DesignProposal: ...


class SequenceDesigner(Protocol):
    def propose_roles(self, task: SequenceRoleTask) -> SequenceRoleProposal: ...
    def propose_interaction(
        self, task: SequenceInteractionTask
    ) -> SequenceInteractionProposal: ...


class ApiDesigner(Protocol):
    def propose(self, task: ApiDesignTask) -> ApiDesignProposal: ...
