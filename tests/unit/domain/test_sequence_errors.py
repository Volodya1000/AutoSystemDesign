"""Tests for sequence-specific domain exception ownership."""

import pytest

import domain.specifications.sequence_validator as validator_module
from domain.exceptions.architecture_errors import ArchitectureValidationError
from domain.exceptions.sequence_errors import (
    AsyncDeliveryModeError,
    SequenceIntegrityError,
    SharedClientLifelineError,
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
    assert validator_module.SequenceIntegrityError is SequenceIntegrityError
    assert validator_module.SharedClientLifelineError is SharedClientLifelineError
    assert validator_module.AsyncDeliveryModeError is AsyncDeliveryModeError
