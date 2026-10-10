"""Task and proposal DTOs crossing the ArchitectureDesigner port."""

from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from application.usage import TokenUsage
from domain.exceptions.architecture_errors import ArchitectureValidationError
from domain.models.scenarios import DesignScenario
from domain.models.topology import ArchitectureGraph

JSON_DECODE_ERROR_TYPE: Final[str] = "json_decode"


class DesignTaskMode(StrEnum):
    """State of the generation loop: first attempt or a repair iteration.

    Application-level concept: the domain knows nothing about LLM attempts.
    """

    INITIAL = "initial"
    REPAIR = "repair"


class ProposalFailureDetail(BaseModel):
    """A single field-level failure of an LLM payload against the graph schema."""

    model_config = ConfigDict(extra="forbid")

    location: str  # JSONPath-style location, e.g. "$.nodes[0].node_type"
    message: str
    error_type: str  # JSON_DECODE_ERROR_TYPE or a pydantic error type


class ValidationErrorFeedback(BaseModel):
    """Validator error mapped into a compact, prompt-friendly form."""

    model_config = ConfigDict(extra="forbid")

    error_code: str
    message: str

    @classmethod
    def from_error(
        cls, error: ArchitectureValidationError
    ) -> "ValidationErrorFeedback":
        return cls(error_code=error.error_code, message=error.message)


class DesignTask(BaseModel):
    """One iteration of the generation loop (wraps the domain scenario).

    DesignScenario is the WHAT (domain); DesignTask is the HOW: the loop
    mode, the previous answer and the accumulated feedback for the repair.
    """

    model_config = ConfigDict(extra="forbid")

    scenario: DesignScenario
    mode: DesignTaskMode
    previous_graph_payload: str | None = None
    validation_feedback: list[ValidationErrorFeedback] = Field(default_factory=list)
    parsing_failures: list[ProposalFailureDetail] = Field(default_factory=list)


class DesignProposal(BaseModel):
    """Parsed LLM proposal.

    `raw_content` is diagnostic-only: it preserves what the model actually
    returned (including fields silently dropped during parsing) and is the
    primary debugging artifact when the capability gate fails.
    """

    model_config = ConfigDict(extra="forbid")

    graph: ArchitectureGraph
    raw_content: str
    usage: TokenUsage
