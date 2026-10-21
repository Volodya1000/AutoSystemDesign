# Copyright (c) 2026 Volodya1000
import pytest

from infrastructure.llm.models import FinishReason

pytestmark = pytest.mark.unit


class TestFinishReason:
    @staticmethod
    def test_maps_known_reasons() -> None:
        assert FinishReason.from_raw("stop") is FinishReason.STOP
        assert FinishReason.from_raw("length") is FinishReason.LENGTH
        assert FinishReason.from_raw("content_filter") is FinishReason.CONTENT_FILTER

    @staticmethod
    def test_maps_unknown_and_missing_to_other() -> None:
        assert FinishReason.from_raw("something_weird") is FinishReason.OTHER
        assert FinishReason.from_raw(None) is FinishReason.OTHER
