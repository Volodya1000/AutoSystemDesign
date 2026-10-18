"""Generation loop limits."""

from application.generation_limits import (
    DEFAULT_SEQUENCE_PARALLELISM,
    MAX_ATTEMPTS,
    MAX_SEQUENCE_PARALLELISM,
    MIN_ATTEMPTS,
    MIN_SEQUENCE_PARALLELISM,
)
from pydantic import BaseModel, ConfigDict, Field


class GenerationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(
        default=3,
        ge=MIN_ATTEMPTS,
        le=MAX_ATTEMPTS,
    )

    sequence_parallelism: int = Field(
        default=DEFAULT_SEQUENCE_PARALLELISM,
        ge=MIN_SEQUENCE_PARALLELISM,
        le=MAX_SEQUENCE_PARALLELISM,
    )
