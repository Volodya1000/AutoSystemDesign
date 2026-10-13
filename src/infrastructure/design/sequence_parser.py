import json
from typing import Any

from pydantic import ValidationError

from application.exceptions.generation_exceptions import DesignProposalParsingError
from application.tasks import JSON_DECODE_ERROR_TYPE, ProposalFailureDetail
from application.usage import TokenUsage
from domain.models.sequence import InteractionScenario
from domain.models.system_design import SystemContextOutput
from infrastructure.design.parser import _format_error_location


def parse_system_context(payload: str, usage: TokenUsage) -> SystemContextOutput:
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
        return SystemContextOutput.model_validate(raw_data)
    except ValidationError as validation_error:
        failure_details = [
            ProposalFailureDetail(
                location=_format_error_location(tuple(entry["loc"])),
                message=entry["msg"],
                error_type=entry["type"],
            )
            for entry in validation_error.errors()
        ]
        raise DesignProposalParsingError(
            raw_content=payload, failure_details=failure_details, usage=usage
        ) from validation_error


def parse_interaction_scenario(payload: str, usage: TokenUsage) -> InteractionScenario:
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
        return InteractionScenario.model_validate(raw_data)
    except ValidationError as validation_error:
        failure_details = [
            ProposalFailureDetail(
                location=_format_error_location(tuple(entry["loc"])),
                message=entry["msg"],
                error_type=entry["type"],
            )
            for entry in validation_error.errors()
        ]
        raise DesignProposalParsingError(
            raw_content=payload, failure_details=failure_details, usage=usage
        ) from validation_error
