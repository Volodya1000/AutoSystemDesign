# Copyright (c) 2026 Volodya1000
"""Rendering of validation feedback and parsing failures for repair prompts.

Every repair prompt in this package shows the model the same block: the
domain-level validation errors followed by the parsing failures, each on
its own numbered line. The surrounding prose differs between prompts, so
the caller supplies the fallback text used when no problems were reported.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from application.tasks import ProposalFailureDetail, ValidationErrorFeedback


def render_feedback(
    validation_feedback: Sequence[ValidationErrorFeedback],
    parsing_failures: Sequence[ProposalFailureDetail],
    *,
    empty_message: str,
) -> str:
    """Render a 'Detected problems' block, or ``empty_message`` if empty.

    The block is a "Detected problems:" header followed by one numbered
    line per error. Validation errors come first (formatted as
    ``[CODE] message``), then parsing failures (``[type] message (at location)``).
    """
    entries: list[str] = [
        f"[{feedback.error_code}] {feedback.message}"
        for feedback in validation_feedback
    ]
    entries.extend(
        f"[{failure.error_type}] {failure.message} (at {failure.location})"
        for failure in parsing_failures
    )
    if not entries:
        return empty_message
    lines: list[str] = ["Detected problems:"]
    lines.extend(f"{index}. {entry}" for index, entry in enumerate(entries, start=1))
    return "\n".join(lines)
