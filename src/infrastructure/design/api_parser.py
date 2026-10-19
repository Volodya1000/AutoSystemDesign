"""ApiDesign parser."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.models.api import ApiDesign
from infrastructure.design._parsing import parse_payload

if TYPE_CHECKING:
    from application.usage import TokenUsage


def parse_api_design(payload: str, usage: TokenUsage) -> ApiDesign:
    """Parses a raw LLM completion into an ApiDesign."""
    return parse_payload(payload, ApiDesign, usage)
