# Copyright (c) 2026 Volodya1000
"""Unit tests of the shared feedback renderer."""

import pytest

from application.tasks import ProposalFailureDetail, ValidationErrorFeedback
from infrastructure.prompts._feedback import render_feedback

pytestmark = pytest.mark.unit


def test_returns_empty_message_when_no_problems() -> None:
    rendered = render_feedback([], [], empty_message="Nothing to fix.")
    assert rendered == "Nothing to fix."


def test_renders_validation_errors_before_parsing_failures() -> None:
    rendered = render_feedback(
        [
            ValidationErrorFeedback(
                error_code="ISOLATED_NODE",
                message="Node 'db' is isolated.",
            )
        ],
        [
            ProposalFailureDetail(
                location="$.nodes[0]",
                message="Field required",
                error_type="missing",
            )
        ],
        empty_message="unused",
    )
    assert rendered == (
        "Detected problems:\n"
        "1. [ISOLATED_NODE] Node 'db' is isolated.\n"
        "2. [missing] Field required (at $.nodes[0])"
    )


def test_header_is_present_when_feedback_exists() -> None:
    rendered = render_feedback(
        [
            ValidationErrorFeedback(
                error_code="BUDGET_EXCEEDED",
                message="over",
            )
        ],
        [],
        empty_message="unused",
    )
    assert rendered.startswith("Detected problems:")
    assert rendered.count("\n") == 1  # header + one entry
