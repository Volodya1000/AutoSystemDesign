"""Backward-compatible imports for sequence validation rules.

New code should import from :mod:`domain.specifications.sequence_validation`.
"""

from domain.exceptions.sequence_errors import (
    AsyncDeliveryModeError,
    SequenceIntegrityError,
    SharedClientLifelineError,
)
from domain.specifications.sequence_validation import (
    __all__ as _sequence_validation_exports,
    ClientOwnershipValidator as ClientOwnershipValidator,
    DeliveryModeValidator as DeliveryModeValidator,
    SequenceCatalogValidator as SequenceCatalogValidator,
    SequenceIntegrityValidator as SequenceIntegrityValidator,
    SequenceScenarioValidator as SequenceScenarioValidator,
)

__all__ = [
    *_sequence_validation_exports,
    "AsyncDeliveryModeError",
    "SequenceIntegrityError",
    "SharedClientLifelineError",
]
