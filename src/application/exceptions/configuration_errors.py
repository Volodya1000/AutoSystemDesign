"""Typed configuration errors for application services."""

from __future__ import annotations



DESIGN_VALIDATOR_KIND = "design"
CATALOG_VALIDATOR_KIND = "catalog"
SCENARIO_VALIDATOR_KIND = "scenario"


class GenerationConfigurationError(ValueError):
    """Invalid retry or validator configuration for a generation service."""

    @classmethod
    def attempts_out_of_range(
        cls, minimum: int, maximum: int, actual: int
    ) -> GenerationConfigurationError:
        return cls(
            f"max_attempts must be between {minimum} and {maximum}, got {actual}"
        )

    @classmethod
    def max_parallel_workers_too_small(
        cls, actual: int
    ) -> GenerationConfigurationError:
        return cls(f"max_parallel_workers must be at least 1, got {actual}")

    @classmethod
    def required_validators_missing(
        cls, validator_kind: str
    ) -> GenerationConfigurationError:
        messages = {
            DESIGN_VALIDATOR_KIND: "At least one validator is required",
            CATALOG_VALIDATOR_KIND: "At least one catalog validator is required",
            SCENARIO_VALIDATOR_KIND: "At least one scenario validator is required",
        }
        return cls(messages[validator_kind])
