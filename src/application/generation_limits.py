"""Application-level limits shared by generation services and configuration."""

from typing import Final

MIN_ATTEMPTS: Final[int] = 1
MAX_ATTEMPTS: Final[int] = 10

MIN_SEQUENCE_PARALLELISM: Final[int] = 1
MAX_SEQUENCE_PARALLELISM: Final[int] = 16
DEFAULT_SEQUENCE_PARALLELISM: Final[int] = 4
