import pytest

from application.usage import TokenUsage

pytestmark = pytest.mark.unit


class TestTokenUsage:
    def test_total_tokens_sums_components(self) -> None:
        usage: TokenUsage = TokenUsage(prompt_tokens=10, completion_tokens=5)
        assert usage.total_tokens == EXPECTED_ASSERT_USAGE_TOTAL_TOKENS

    def test_aggregate_sums_all_usages(self) -> None:
        aggregate: TokenUsage = TokenUsage.aggregate(
            [
                TokenUsage(prompt_tokens=10, completion_tokens=5),
                TokenUsage(prompt_tokens=1, completion_tokens=2),
            ]
        )
        assert aggregate == TokenUsage(prompt_tokens=11, completion_tokens=7)
        assert aggregate.estimated is False

    def test_aggregate_marks_estimated_when_any_input_is_estimated(self) -> None:
        aggregate: TokenUsage = TokenUsage.aggregate(
            [
                TokenUsage(prompt_tokens=10, completion_tokens=5),
                TokenUsage(prompt_tokens=1, completion_tokens=2, estimated=True),
            ]
        )
        assert aggregate.estimated is True

    def test_aggregate_of_nothing_is_zero(self) -> None:
        assert TokenUsage.aggregate([]) == TokenUsage(
            prompt_tokens=0, completion_tokens=0
        )

EXPECTED_ASSERT_USAGE_TOTAL_TOKENS = 15

