# Copyright (c) 2026 Volodya1000
"""Typed validation errors for domain model invariants."""

from enum import StrEnum
from typing import ClassVar


class ModelValidationCode(StrEnum):
    """Stable identifiers for model and topology validation failures."""

    API_ARRAY_REQUIRES_ITEM_TYPE = "api.array_requires_item_type"
    API_NON_ARRAY_FORBIDS_ITEM_TYPE = "api.non_array_forbids_item_type"
    API_PATH_PARAMETER_REQUIRED = "api.path_parameter_required"
    API_INVALID_STATUS_CODE = "api.invalid_status_code"
    API_DUPLICATE_RESPONSE_STATUS_CODE = "api.duplicate_response_status_code"
    ALT_ELSE_BRANCH_MUST_BE_LAST = "sequence.alt_else_branch_must_be_last"
    ALT_CONDITION_MUST_NOT_BE_EMPTY = "sequence.alt_condition_must_not_be_empty"
    ALT_SINGLE_ELSE_BRANCH = "sequence.alt_single_else_branch"
    INVALID_INTERVAL_BOUNDS = "requirements.invalid_interval_bounds"
    ABSTRACT_BASE_NODE = "topology.abstract_base_node"
    ABSTRACT_CAPACITY_NODE = "topology.abstract_capacity_node"
    WORKLOAD_PEAK_BELOW_BASELINE = "scenario.workload_peak_below_baseline"
    EMPTY_LIFELINE_ID = "sequence.empty_lifeline_id"
    DUPLICATE_LIFELINE_ID = "sequence.duplicate_lifeline_id"
    UNKNOWN_MESSAGE_SENDER = "sequence.unknown_message_sender"
    UNKNOWN_MESSAGE_RECIPIENT = "sequence.unknown_message_recipient"
    UNUSED_LIFELINES = "sequence.unused_lifelines"
    TOPOLOGY_CYCLE = "topology.cycle"
    DUPLICATE_REQUIREMENT_VALIDATOR = "requirements.duplicate_validator"


class ModelValidationError(ValueError):
    """A domain validation error with a stable code and centralized message."""

    code: ModelValidationCode

    _MESSAGES: ClassVar[dict[ModelValidationCode, str]] = {
        ModelValidationCode.API_ARRAY_REQUIRES_ITEM_TYPE: (
            "Parameter '{name}' has data_type='array' but 'item_type' is not defined."
        ),
        ModelValidationCode.API_NON_ARRAY_FORBIDS_ITEM_TYPE: (
            "Parameter '{name}' must not define 'item_type' "
            "when data_type is '{data_type}'."
        ),
        ModelValidationCode.API_PATH_PARAMETER_REQUIRED: (
            "Path parameter '{name}' must always have required=True."
        ),
        ModelValidationCode.API_INVALID_STATUS_CODE: (
            "Invalid HTTP status code '{status_code}'. "
            "Must be a 3-digit code or 'default'."
        ),
        ModelValidationCode.API_DUPLICATE_RESPONSE_STATUS_CODE: (
            "Duplicate response status code '{status_code}' "
            "in operation '{operation_id}'."
        ),
        ModelValidationCode.ALT_ELSE_BRANCH_MUST_BE_LAST: (
            "The default branch (else / condition=None) must be "
            "the last one in an alt block."
        ),
        ModelValidationCode.ALT_CONDITION_MUST_NOT_BE_EMPTY: (
            "A conditional branch cannot have an empty condition "
            "or consist only of spaces."
        ),
        ModelValidationCode.ALT_SINGLE_ELSE_BRANCH: (
            "An 'alt' block can contain only one default (else) branch."
        ),
        ModelValidationCode.INVALID_INTERVAL_BOUNDS: (
            "minimum_value must be less than or equal to maximum_value"
        ),
        ModelValidationCode.ABSTRACT_BASE_NODE: (
            "BaseNode is abstract: instantiate a concrete node subclass"
        ),
        ModelValidationCode.ABSTRACT_CAPACITY_NODE: (
            "CapacityNode is abstract: instantiate a concrete node subclass"
        ),
        ModelValidationCode.WORKLOAD_PEAK_BELOW_BASELINE: (
            "peak_requests_per_second must be greater than or equal "
            "to baseline_requests_per_second"
        ),
        ModelValidationCode.EMPTY_LIFELINE_ID: (
            "Lifeline identifier (lifeline_id) cannot be empty."
        ),
        ModelValidationCode.DUPLICATE_LIFELINE_ID: (
            "Duplicate lifeline identifier: '{lifeline_id}'"
        ),
        ModelValidationCode.UNKNOWN_MESSAGE_SENDER: (
            "Unknown message sender: '{lifeline_id}'"
        ),
        ModelValidationCode.UNKNOWN_MESSAGE_RECIPIENT: (
            "Unknown message recipient: '{lifeline_id}'"
        ),
        ModelValidationCode.UNUSED_LIFELINES: (
            "Declared lifelines never participate in any message: {unused}. "
            "Every lifeline must appear in at least one message step; "
            "remove unused lifelines from the 'lifelines' array."
        ),
        ModelValidationCode.TOPOLOGY_CYCLE: (
            "Graph contains a cycle; topology must be a DAG"
        ),
        ModelValidationCode.DUPLICATE_REQUIREMENT_VALIDATOR: (
            "Duplicate RequirementValidator for {requirement_type}"
        ),
    }

    def __init__(self, code: ModelValidationCode, **context: object) -> None:
        self.code = code
        super().__init__(self._MESSAGES[code].format(**context))
