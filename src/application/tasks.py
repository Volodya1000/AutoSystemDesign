from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from application.usage import TokenUsage
from domain.exceptions.architecture_errors import ArchitectureValidationError
from domain.models.functional import FunctionalRequirement
from domain.models.roles import ProjectRolesCatalog
from domain.models.scenarios import DesignScenario
from domain.models.sequence import InteractionScenario
from domain.models.topology import ArchitectureGraph

JSON_DECODE_ERROR_TYPE: Final[str] = "json_decode"


class DesignTaskMode(StrEnum):
    INITIAL = "initial"
    REPAIR = "repair"


class ProposalFailureDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: str
    message: str
    error_type: str


class ValidationErrorFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_code: str
    message: str

    @classmethod
    def from_error(
        cls, error: ArchitectureValidationError
    ) -> "ValidationErrorFeedback":
        return cls(error_code=error.error_code, message=error.message)


class DesignTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: DesignScenario
    mode: DesignTaskMode
    previous_graph_payload: str | None = None
    validation_feedback: list[ValidationErrorFeedback] = Field(default_factory=list)
    parsing_failures: list[ProposalFailureDetail] = Field(default_factory=list)


class DesignProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    graph: ArchitectureGraph
    raw_content: str
    usage: TokenUsage
    latency_seconds: float = Field(default=0.0, ge=0.0)


class SequenceRoleTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: DesignScenario
    mode: DesignTaskMode
    previous_payload: str | None = None
    validation_feedback: list[ValidationErrorFeedback] = Field(default_factory=list)
    parsing_failures: list[ProposalFailureDetail] = Field(default_factory=list)


class SequenceRoleProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload: ProjectRolesCatalog
    raw_content: str
    usage: TokenUsage
    latency_seconds: float = Field(default=0.0, ge=0.0)


class SequenceInteractionTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement: FunctionalRequirement
    roles_catalog: ProjectRolesCatalog
    architecture_graph: ArchitectureGraph
    mode: DesignTaskMode
    previous_payload: str | None = None
    validation_feedback: list[ValidationErrorFeedback] = Field(default_factory=list)
    parsing_failures: list[ProposalFailureDetail] = Field(default_factory=list)


class SequenceInteractionProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload: InteractionScenario
    raw_content: str
    usage: TokenUsage
    latency_seconds: float = Field(default=0.0, ge=0.0)
