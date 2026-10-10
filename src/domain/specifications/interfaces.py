from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict, Field

from domain.exceptions.architecture_errors import ArchitectureValidationError
from domain.models.topology import ArchitectureGraph


class ValidationResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    is_successful: bool
    errors: list[ArchitectureValidationError] = Field(default_factory=list)

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
