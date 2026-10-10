"""Ports (protocols) implemented by infrastructure agents."""

from typing import Protocol

from application.tasks import DesignProposal, DesignTask


class ArchitectureDesigner(Protocol):
    """LLM-backed architect producing an ArchitectureGraph for a DesignTask.

    Implementations raise DesignProposalParsingError when the model output
    cannot be parsed; infrastructure-level failures (network, timeout)
    propagate as infrastructure errors and must not be swallowed.
    """

    def propose(self, task: DesignTask) -> DesignProposal: ...
