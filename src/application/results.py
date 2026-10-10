"""Result DTOs of the design generation loop."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from application.usage import TokenUsage
from domain.models.topology import ArchitectureGraph
from domain.specifications.interfaces import ValidationResult


class GenerationStatus(StrEnum):
    SUCCEEDED = "succeeded"
    VALIDATION_FAILED = "validation_failed"
    PARSING_FAILED = "parsing_failed"


class GenerationAttempt(BaseModel):
    """Outcome of a single generation attempt within the repair loop."""

    model_config = ConfigDict(extra="forbid")

    attempt_number: int = Field(ge=1)
    parsed: bool
    graph: ArchitectureGraph | None = None
    validation: ValidationResult | None = None
    usage: TokenUsage


class DesignGenerationResult(BaseModel):
    """Final result of the generation loop; status is derived, never stored."""

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
        """The most recent graph that was parsed successfully, if any."""
        for attempt in reversed(self.attempts):
            if attempt.graph is not None:
                return attempt.graph
        return None

    @property
    def total_usage(self) -> TokenUsage:
        return TokenUsage.aggregate(attempt.usage for attempt in self.attempts)
