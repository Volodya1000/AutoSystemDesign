# Copyright (c) 2026 Volodya1000
from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict, Field

from domain.exceptions.architecture_errors import ArchitectureValidationError
from domain.models.base_constraints import BaseRequirement
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
        raise NotImplementedError


class ScenarioValidator(ABC):
    """Abstract interface for validators that check a graph against a scenario.

    Workload-driven validators (F3 flow computation, F4 utilization, ...)
    still live behind this port. Requirement-driven validators use the
    narrower RequirementValidator port and are aggregated by
    RequirementValidationDispatcher.
    """

    @abstractmethod
    def validate(
        self, graph: ArchitectureGraph, scenario: DesignScenario
    ) -> ValidationResult:
        raise NotImplementedError


class RequirementValidator[ReqT: BaseRequirement](ABC):
    """Abstract interface for validators that check exactly one requirement.

    Concrete implementations declare `requirement_type` and receive only
    requirements of that type: the narrow input keeps each validator small
    (SRP) and free of isinstance-scanning (ISP).
    """

    requirement_type: type[ReqT]

    @abstractmethod
    def validate(
        self, graph: ArchitectureGraph, requirement: ReqT
    ) -> list[ArchitectureValidationError]:
        raise NotImplementedError
