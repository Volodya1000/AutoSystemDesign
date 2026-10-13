from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from application.tasks import ProposalFailureDetail
from application.usage import TokenUsage
from domain.models.roles import ProjectRolesCatalog
from domain.models.sequence import InteractionScenario
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
    payload: Any | None = None
    validation: ValidationResult | None = None
    usage: TokenUsage = Field(default_factory=TokenUsage)
    latency_seconds: float = Field(default=0.0, ge=0.0)
    parsing_failures: list[ProposalFailureDetail] = Field(default_factory=list)


class DesignGenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempts: list[GenerationAttempt] = Field(min_length=1)

    @property
    def status(self) -> GenerationStatus:
        last_attempt = self.attempts[-1]
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


class SequenceScenarioResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempts: list[GenerationAttempt] = Field(default_factory=list)
    interaction_scenario: InteractionScenario | None = None

    @property
    def is_successful(self) -> bool:
        return self.interaction_scenario is not None


class SequenceGenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roles_attempts: list[GenerationAttempt] = Field(default_factory=list)
    roles_catalog: ProjectRolesCatalog | None = None
    scenarios_results: dict[str, SequenceScenarioResult] = Field(default_factory=dict)

    @property
    def is_successful(self) -> bool:
        if self.roles_catalog is None or not self.scenarios_results:
            return False
        return all(s.is_successful for s in self.scenarios_results.values())

    @property
    def total_usage(self) -> TokenUsage:
        usages: list[TokenUsage] = [a.usage for a in self.roles_attempts]
        for s in self.scenarios_results.values():
            usages.extend(a.usage for a in s.attempts)
        return TokenUsage.aggregate(usages)
