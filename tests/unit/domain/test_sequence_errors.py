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
    ("exception_type", "error_code"),
    [
        (SequenceIntegrityError, "SEQUENCE_INTEGRITY_ERROR"),
        (SharedClientLifelineError, "SHARED_CLIENT_LIFELINE"),
        (AsyncDeliveryModeError, "ASYNC_DELIVERY_MODE_REQUIRED"),
    ],
)
def test_sequence_exceptions_remain_architecture_validation_errors(
    exception_type: type[ArchitectureValidationError],
    error_code: str,
) -> None:
    error = exception_type("test error")

    assert isinstance(error, ArchitectureValidationError)
    assert error.error_code == error_code


def test_sequence_exceptions_keep_legacy_validator_module_imports() -> None:
    assert ValidatorSequenceIntegrityError is SequenceIntegrityError
    assert ValidatorSharedClientLifelineError is SharedClientLifelineError
    assert ValidatorAsyncDeliveryModeError is AsyncDeliveryModeError
