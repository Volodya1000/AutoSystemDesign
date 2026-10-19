"""Application-level import path for shared generation policy constants.

The constants are defined in `shared.generation_limits` so configuration and
application code can use the same limits without depending on one another.
"""

from shared.generation_limits import (
    DEFAULT_SEQUENCE_PARALLELISM,
    MAX_ATTEMPTS,
    MAX_SEQUENCE_PARALLELISM,
    MIN_ATTEMPTS,
    MIN_SEQUENCE_PARALLELISM,
)

__all__ = [
    "DEFAULT_SEQUENCE_PARALLELISM",
    "MAX_ATTEMPTS",
    "MAX_SEQUENCE_PARALLELISM",
    "MIN_ATTEMPTS",
    "MIN_SEQUENCE_PARALLELISM",
]
