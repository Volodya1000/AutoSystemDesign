"""Regression tests for extracting JSON from LLM completion text."""

import pytest

from infrastructure.design._parsing import extract_json_payload


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"items": []}', '{"items": []}'),
        ('{"items": []} trailing commentary', '{"items": []}'),
        ('Here is the result: {"items": []} done', '{"items": []}'),
        ('<think>reasoning {not json}</think>{"items": []}', '{"items": []}'),
        ('<think>reasoning</think>\n```json\n{"items": []}\n```', '{"items": []}'),
        ('<THINK>reasoning</THINK>{"items": []}', '{"items": []}'),
        ('```json\n{"items": {"nested": true}}\n```', '{"items": {"nested": true}}'),
    ],
)
def test_extract_json_payload(raw: str, expected: str) -> None:
    assert extract_json_payload(raw) == expected


def test_extract_json_payload_returns_unparseable_text_when_no_object_exists() -> None:
    raw = "No JSON was generated."

    assert extract_json_payload(raw) == raw
