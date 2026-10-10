"""Extraction and parsing of the JSON payload produced by the LLM."""

import json
import re
from typing import Any

from pydantic import ValidationError

from application.exceptions.generation_exceptions import DesignProposalParsingError
from application.tasks import JSON_DECODE_ERROR_TYPE, ProposalFailureDetail
from application.usage import TokenUsage
from domain.models.topology import ArchitectureGraph

_THINK_BLOCK_PATTERN: re.Pattern[str] = re.compile(r"", re.DOTALL)
_CODE_FENCE_PATTERN: re.Pattern[str] = re.compile(
    r"```[a-zA-Z]*\s*(.*?)\s*```", re.DOTALL
)


def extract_json_payload(raw: str) -> str:
    """Extracts the JSON payload from a raw LLM completion.

    Steps: strip Qwen-style  think blocks, unwrap markdown code fences, then
    fall back to the substring between the first '{' and the last '}'.
    """
    text: str = _THINK_BLOCK_PATTERN.sub("", raw).strip()
    fenced_match: re.Match[str] | None = _CODE_FENCE_PATTERN.search(text)
    if fenced_match is not None:
        text = fenced_match.group(1).strip()
    if not text.startswith("{"):
        first_brace: int = text.find("{")
        last_brace: int = text.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            text = text[first_brace : last_brace + 1]
    return text.strip()


def parse_architecture_graph(payload: str, usage: TokenUsage) -> ArchitectureGraph:
    """Parses a JSON payload into an ArchitectureGraph.

    Raises DesignProposalParsingError with field-level failure details for
    both JSON-level and schema-level problems.
    """
    try:
        raw_data: Any = json.loads(payload)
    except json.JSONDecodeError as decode_error:
        raise DesignProposalParsingError(
            raw_content=payload,
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
        return ArchitectureGraph.model_validate(raw_data)
    except ValidationError as validation_error:
        failure_details: list[ProposalFailureDetail] = [
            ProposalFailureDetail(
                location=_format_error_location(tuple(entry["loc"])),
                message=entry["msg"],
                error_type=entry["type"],
            )
            for entry in validation_error.errors()
        ]
        raise DesignProposalParsingError(
            raw_content=payload,
            failure_details=failure_details,
            usage=usage,
        ) from validation_error


def _format_error_location(loc: tuple[int | str, ...]) -> str:
    """Formats a pydantic error location as a JSONPath-like string."""
    if not loc:
        return "$"
    path: str = str(loc[0])
    for part in loc[1:]:
        if isinstance(part, int):
            path = f"{path}[{part}]"
        else:
            path = f"{path}.{part}"
    return f"$.{path}"
