"""ApiDesign parser."""

from __future__ import annotations

from application.usage import TokenUsage
from domain.models.api import ApiDesign
from infrastructure.design._parsing import parse_payload


def parse_api_design(payload: str, usage: TokenUsage) -> ApiDesign:
    """Parses a raw LLM completion into an ApiDesign."""
    return parse_payload(payload, ApiDesign, usage)
