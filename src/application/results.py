from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from application.tasks import ProposalFailureDetail
from application.usage import TokenUsage
from domain.models.system_design import SystemDesignOutput
from domain.models.topology import ArchitectureGraph
from domain.specifications.interfaces import ValidationResult


class GenerationStatus(StrEnum):
    SUCCEEDED = "succeeded"
    VALIDATION_FAILED = "validation_failed"
    PARSING_FAILED = "parsing_failed"


class GenerationAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_number: int = Field(ge=1)
    parsed: bool
    graph: ArchitectureGraph | None = None
    validation: ValidationResult | None = None
    usage: TokenUsage
    latency_seconds: float = Field(default=0.0, ge=0.0)
    parsing_failures: list[ProposalFailureDetail] = Field(default_factory=list)


class SequenceGenerationAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_number: int = Field(ge=1)
    parsed: bool
    system_design: SystemDesignOutput | None = None
    validation: ValidationResult | None = None
    usage: TokenUsage
    latency_seconds: float = Field(default=0.0, ge=0.0)
    parsing_failures: list[ProposalFailureDetail] = Field(default_factory=list)


class DesignGenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempts: list[GenerationAttempt] = Field(min_length=1)

    @property
    def status(self) -> GenerationStatus:
        last_attempt: GenerationAttempt = self.attempts[-1]
        if not last_attempt.parsed:
            return GenerationStatus.PARSING_FAILED
        if (
            last_attempt.validation is not None
            and last_attempt.validation.is_successful
        ):
            return GenerationStatus.SUCCEEDED
        return GenerationStatus.VALIDATION_FAILED

    @property
    def graph(self) -> ArchitectureGraph | None:
        for attempt in reversed(self.attempts):
            if attempt.graph is not None:
                return attempt.graph
        return None

    @property
    def total_usage(self) -> TokenUsage:
        return TokenUsage.aggregate(attempt.usage for attempt in self.attempts)


class SequenceGenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempts: list[SequenceGenerationAttempt] = Field(min_length=1)

    @property
    def status(self) -> GenerationStatus:
        last_attempt: SequenceGenerationAttempt = self.attempts[-1]
        if not last_attempt.parsed:
            return GenerationStatus.PARSING_FAILED
        if (
            last_attempt.validation is not None
            and last_attempt.validation.is_successful
        ):
            return GenerationStatus.SUCCEEDED
        return GenerationStatus.VALIDATION_FAILED

    @property
    def system_design(self) -> SystemDesignOutput | None:
        for attempt in reversed(self.attempts):
            if attempt.system_design is not None:
                return attempt.system_design
        return None

    @property
    def total_usage(self) -> TokenUsage:
        return TokenUsage.aggregate(attempt.usage for attempt in self.attempts)
