"""Shared JSON-extraction and payload-parsing helpers for the design package.

``extract_json_payload`` strips markdown fences and Qwen-style think blocks
from a raw LLM completion. ``parse_payload`` combines it with pydantic
validation and maps both JSON and schema errors to
``DesignProposalParsingError``. Every parser in this package is a one-liner
wrapping ``parse_payload``.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ValidationError

from application.exceptions.generation_exceptions import DesignProposalParsingError
from application.tasks import JSON_DECODE_ERROR_TYPE, ProposalFailureDetail
from infrastructure.design._error_location import format_error_location

if TYPE_CHECKING:
    from application.usage import TokenUsage

_THINK_BLOCK_PATTERN: re.Pattern[str] = re.compile(
    r"<think>.*?</think>", re.DOTALL | re.IGNORECASE
)
_CODE_FENCE_PATTERN: re.Pattern[str] = re.compile(
    r"```[a-zA-Z]*\s*(.*?)\s*```", re.DOTALL
)


def extract_json_payload(raw: str) -> str:
    """Extract a JSON object from an LLM completion.

    Think blocks and markdown fences are removed first. A JSON decoder then
    identifies the first complete object, including when non-JSON commentary
    follows it. If no complete object can be decoded, the remaining text is
    returned unchanged so the caller can report a normal JSON decoding error.
    """
    text: str = _THINK_BLOCK_PATTERN.sub("", raw).strip()
    fenced_match: re.Match[str] | None = _CODE_FENCE_PATTERN.search(text)
    if fenced_match is not None:
        text = fenced_match.group(1).strip()

    first_brace: int = text.find("{")
    if first_brace == -1:
        return text

    try:
        _, end_index = json.JSONDecoder().raw_decode(text, first_brace)
    except json.JSONDecodeError:
        return text
    return text[first_brace:end_index].strip()


def parse_payload[ModelT: BaseModel](
    text: str, model: type[ModelT], usage: TokenUsage
) -> ModelT:
    """Extract JSON from ``text`` and validate it against ``model``.

    On failure raises ``DesignProposalParsingError`` carrying the original
    text (before extraction) so repair prompts can show the model what it
    actually emitted, including any fences or think blocks.
    """
    extracted: str = extract_json_payload(text)
    try:
        raw_data: Any = json.loads(extracted)
    except json.JSONDecodeError as decode_error:
        raise DesignProposalParsingError(
            raw_content=text,
            failure_details=[
                ProposalFailureDetail(
                    location="$",
                    message=str(decode_error),
                    error_type=JSON_DECODE_ERROR_TYPE,
                )
            ],
            usage=usage,
        ) from decode_error

    try:
        return model.model_validate(raw_data)
    except ValidationError as validation_error:
        failure_details: list[ProposalFailureDetail] = [
            ProposalFailureDetail(
                location=format_error_location(tuple(entry["loc"])),
                message=entry["msg"],
                error_type=entry["type"],
            )
            for entry in validation_error.errors()
        ]
        raise DesignProposalParsingError(
            raw_content=text,
            failure_details=failure_details,
            usage=usage,
        ) from validation_error
