"""Property-based checks of core domain invariants."""

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from domain.models.base_constraints import IntervalRequirement
from domain.models.scenarios import DesignScenario, WorkloadProfile

pytestmark: pytest.MarkDecorator = pytest.mark.unit

_FIRST_CHARACTERS: str = (
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
)
_REMAINING_CHARACTERS: str = _FIRST_CHARACTERS + "_-"


@settings(max_examples=100, deadline=None)
@given(
    baseline=st.floats(min_value=0.1, max_value=100_000),
    increment=st.floats(min_value=0.1, max_value=100_000),
    read_ratio=st.floats(min_value=0.0, max_value=1.0),
)
def test_workload_maintains_valid_rates_and_ratio(
    baseline: float, increment: float, read_ratio: float
) -> None:
    """Accepted workloads preserve rates and complementary ratios."""
    profile: WorkloadProfile = WorkloadProfile(
        baseline_requests_per_second=baseline,
        peak_requests_per_second=baseline + increment,
        read_ratio=read_ratio,
    )

    assert profile.peak_requests_per_second >= profile.baseline_requests_per_second
    assert math.isclose(
        profile.read_ratio + profile.write_ratio,
        1.0,
        abs_tol=1e-12,
    )


@settings(max_examples=100, deadline=None)
@given(
    peak=st.floats(min_value=0.1, max_value=100_000),
    gap=st.floats(min_value=0.1, max_value=100_000),
)
def test_workload_rejects_peak_below_baseline(
    peak: float, gap: float
) -> None:
    """Peak traffic must not be lower than baseline traffic."""
    with pytest.raises(ValidationError):
        WorkloadProfile(
            baseline_requests_per_second=peak + gap,
            peak_requests_per_second=peak,
        )


@settings(max_examples=100, deadline=None)
@given(
    minimum=st.floats(min_value=-100_000, max_value=100_000),
    width=st.floats(min_value=0.0, max_value=100_000),
)
def test_interval_requirement_observes_inclusive_bounds(
    minimum: float, width: float
) -> None:
    """An interval accepts its bounds and rejects exterior points."""
    maximum: float = minimum + width
    requirement: IntervalRequirement = IntervalRequirement(
        minimum_value=minimum,
        maximum_value=maximum,
    )

    assert requirement.is_met_requirement(minimum)
    assert requirement.is_met_requirement(maximum)
    assert not requirement.is_met_requirement(minimum - 1.0)
    assert not requirement.is_met_requirement(maximum + 1.0)


@settings(max_examples=100, deadline=None)
@given(
    first=st.sampled_from(tuple(_FIRST_CHARACTERS)),
    rest=st.text(alphabet=_REMAINING_CHARACTERS, max_size=30),
)
def test_scenario_accepts_safe_artifact_identifiers(
    first: str, rest: str
) -> None:
    """Valid, path-safe artifact identifiers survive model validation."""
    identifier: str = first + rest
    scenario: DesignScenario = DesignScenario(
        identifier=identifier,
        description="Property-based scenario validation",
    )

    assert scenario.identifier == identifier


@settings(max_examples=100, deadline=None)
@given(identifier=st.text(alphabet="/\\. ", min_size=1, max_size=15))
def test_scenario_rejects_unsafe_artifact_identifiers(
    identifier: str,
) -> None:
    """Path separators, whitespace, and leading dots are forbidden."""
    with pytest.raises(ValidationError):
        DesignScenario(
            identifier=identifier,
            description="Property-based scenario validation",
        )
