"""Generation loop limits."""

from typing import Final

from pydantic import BaseModel, ConfigDict, Field

MIN_ATTEMPTS: Final[int] = 1
MAX_ATTEMPTS: Final[int] = 10

MIN_SEQUENCE_PARALLELISM: Final[int] = 1
MAX_SEQUENCE_PARALLELISM: Final[int] = 16
DEFAULT_SEQUENCE_PARALLELISM: Final[int] = 4


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
