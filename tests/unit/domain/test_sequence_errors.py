"""Tests for sequence-specific domain exception ownership."""

import pytest

from domain.exceptions.architecture_errors import ArchitectureValidationError
from domain.exceptions.sequence_errors import (
    AsyncDeliveryModeError,
    SequenceIntegrityError,
    SharedClientLifelineError,
)
from domain.specifications.sequence_validator import (
    AsyncDeliveryModeError as ValidatorAsyncDeliveryModeError,
    SequenceIntegrityError as ValidatorSequenceIntegrityError,
    SharedClientLifelineError as ValidatorSharedClientLifelineError,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("error", "expected_error_code"),
    [
        (SequenceIntegrityError("broken reference"), "SEQUENCE_INTEGRITY_ERROR"),
        (
            SharedClientLifelineError("client", ["buyer", "admin"]),
            "SHARED_CLIENT_LIFELINE",
        ),
        (
            AsyncDeliveryModeError("publish event", "event"),
            "ASYNC_DELIVERY_MODE_REQUIRED",
        ),
    ],
)
def test_sequence_exceptions_remain_architecture_validation_errors(
    error: ArchitectureValidationError,
    expected_error_code: str,
) -> None:
    assert error.error_code == expected_error_code


def test_sequence_exceptions_keep_legacy_validator_module_imports() -> None:
    assert ValidatorSequenceIntegrityError is SequenceIntegrityError
    assert ValidatorSharedClientLifelineError is SharedClientLifelineError
    assert ValidatorAsyncDeliveryModeError is AsyncDeliveryModeError
