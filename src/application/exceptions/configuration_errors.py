"""Typed configuration errors for application services."""

from __future__ import annotations


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
            "design": "At least one validator is required",
            "catalog": "At least one catalog validator is required",
            "scenario": "At least one scenario validator is required",
        }
        return cls(messages[validator_kind])
