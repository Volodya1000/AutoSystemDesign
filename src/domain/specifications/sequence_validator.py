# Copyright (c) 2026 Volodya1000
"""Backward-compatible imports for sequence validation rules.

New code should import from :mod:`domain.specifications.sequence_validation`.
"""

from domain.exceptions.sequence_errors import (
    AsyncDeliveryModeError,
    SequenceIntegrityError,
    SharedClientLifelineError,
)
from domain.specifications.sequence_validation import (
    ClientOwnershipValidator,
    DeliveryModeValidator,
    SequenceCatalogValidator,
    SequenceIntegrityValidator,
    SequenceScenarioValidator,
)

__all__ = [
    "AsyncDeliveryModeError",
    "ClientOwnershipValidator",
    "DeliveryModeValidator",
    "SequenceCatalogValidator",
    "SequenceIntegrityError",
    "SequenceIntegrityValidator",
    "SequenceScenarioValidator",
    "SharedClientLifelineError",
]
