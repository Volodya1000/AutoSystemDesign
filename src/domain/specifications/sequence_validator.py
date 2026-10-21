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
    SequenceCatalogValidatorProtocol,
    SequenceIntegrityValidator,
    SequenceScenarioValidatorProtocol,
)

__all__ = [
    "AsyncDeliveryModeError",
    "ClientOwnershipValidator",
    "DeliveryModeValidator",
    "SequenceCatalogValidatorProtocol",
    "SequenceIntegrityError",
    "SequenceIntegrityValidator",
    "SequenceScenarioValidatorProtocol",
    "SharedClientLifelineError",
]
