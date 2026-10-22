"""Verify numerical requirement boundaries through their public behavior."""

import pytest
from pydantic import ValidationError

from domain.models.base_constraints import IntervalRequirement, ThresholdRequirement
from domain.models.enums import Operator

pytestmark: pytest.MarkDecorator = pytest.mark.unit


@pytest.mark.parametrize(
    ("operator", "expected"),
    [
        (Operator.LESS_THAN, (True, False, False)),
        (Operator.LESS_THAN_OR_EQUAL, (True, True, False)),
        (Operator.EQUAL, (False, True, False)),
        (Operator.GREATER_THAN_OR_EQUAL, (False, True, True)),
        (Operator.GREATER_THAN, (False, False, True)),
    ],
)
def test_threshold_distinguishes_below_equal_and_above(
    operator: Operator, expected: tuple[bool, bool, bool]
) -> None:
    requirement: ThresholdRequirement = ThresholdRequirement(
        threshold_value=10.0, operator=operator
    )

    observed: tuple[bool, bool, bool] = (
        requirement.is_met_requirement(9.0),
        requirement.is_met_requirement(10.0),
        requirement.is_met_requirement(11.0),
    )

    assert observed == expected


@pytest.mark.parametrize(
    ("actual", "expected"), [(10.0 + 1e-10, True), (10.001, False)]
)
def test_equality_tolerates_rounding_but_rejects_meaningful_difference(
    actual: float, *, expected: bool
) -> None:
    requirement: ThresholdRequirement = ThresholdRequirement(
        threshold_value=10.0, operator=Operator.EQUAL
    )

    assert requirement.is_met_requirement(actual) is expected


@pytest.mark.parametrize(
    ("actual", "expected"),
    [(-1.0, False), (0.0, True), (5.0, True), (10.0, True), (11.0, False)],
)
def test_interval_accepts_both_bounds_and_rejects_exterior_values(
    actual: float, *, expected: bool
) -> None:
    requirement: IntervalRequirement = IntervalRequirement(
        minimum_value=0.0, maximum_value=10.0
    )

    assert requirement.is_met_requirement(actual) is expected


def test_single_point_interval_accepts_only_its_bound() -> None:
    requirement: IntervalRequirement = IntervalRequirement(
        minimum_value=5.0, maximum_value=5.0
    )

    assert requirement.is_met_requirement(5.0)
    assert not requirement.is_met_requirement(4.0)
    assert not requirement.is_met_requirement(6.0)


def test_interval_rejects_reversed_bounds() -> None:
    with pytest.raises(ValidationError):
        IntervalRequirement(minimum_value=10.0, maximum_value=0.0)
