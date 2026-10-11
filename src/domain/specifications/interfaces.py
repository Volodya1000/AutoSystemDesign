from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict, Field

from domain.exceptions.architecture_errors import ArchitectureValidationError
from domain.models.scenarios import DesignScenario
from domain.models.topology import ArchitectureGraph


class ValidationResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    errors: list[ArchitectureValidationError] = Field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return not self.errors

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def has_error(self, error_type: type[ArchitectureValidationError]) -> bool:
        """Type-safe check whether a specific domain error occurred."""
        return any(isinstance(error, error_type) for error in self.errors)


class BaseValidator(ABC):
    """Abstract interface for all architecture validators."""

    @abstractmethod
    def validate(self, graph: ArchitectureGraph) -> ValidationResult:
        raise NotImplementedError()


class ScenarioValidator(ABC):
    """Abstract interface for validators that check a graph against a scenario.

    Scenario validators verify workload-dependent guarantees (budget,
    resource utilization, latency) and therefore need the DesignScenario.
    Implementations must tolerate graphs that already failed structural
    validation: skip what cannot be checked and report via errors instead
    of raising.
    """

    @abstractmethod
    def validate(
        self, graph: ArchitectureGraph, scenario: DesignScenario
    ) -> ValidationResult:
        raise NotImplementedError()
