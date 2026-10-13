"""Domain models for functional requirements."""

from pydantic import BaseModel, ConfigDict


class FunctionalRequirement(BaseModel):
    """Specification of a single functional requirement."""

    model_config = ConfigDict(extra="forbid")

    identifier: str
    name: str
    text: str
