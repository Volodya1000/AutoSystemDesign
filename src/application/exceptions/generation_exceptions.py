"""Application-level exceptions of the design generation loop."""

from application.tasks import ProposalFailureDetail
from application.usage import TokenUsage


class DesignProposalParsingError(Exception):
    """Raised when an LLM completion cannot be parsed into an ArchitectureGraph.

    Tokens spent on the failed attempt are preserved in `usage` so the
    generation loop can account for them.
    """

    def __init__(
        self,
        raw_content: str,
        failure_details: list[ProposalFailureDetail],
        usage: TokenUsage,
    ) -> None:
        super().__init__(
            "Failed to parse the LLM proposal into an ArchitectureGraph: "
            + "; ".join(detail.message for detail in failure_details)
        )
        self.raw_content = raw_content
        self.failure_details = failure_details
        self.usage = usage
