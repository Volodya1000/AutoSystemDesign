"""Generation loop limits."""

from typing import Final

from pydantic import BaseModel, ConfigDict, Field

MIN_ATTEMPTS: Final[int] = 1
MAX_ATTEMPTS: Final[int] = 10


class GenerationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(
        default=3,
        ge=MIN_ATTEMPTS,
        le=MAX_ATTEMPTS,
    )
