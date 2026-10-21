# Copyright (c) 2026 Volodya1000
"""Integration test run settings."""

from pydantic import BaseModel, ConfigDict, Field


class IntegrationSettings(BaseModel):
    """Run parameters of the LLM integration test suite.

    Named IntegrationSettings (not TestingSettings) on purpose: pytest tries
    to collect every class matching Test* as a test class.
    """

    model_config = ConfigDict(extra="forbid")

    generation_runs: int = Field(default=3, ge=1, le=10)
    min_single_shot_success_rate: float = Field(default=1.0, ge=0.0, le=1.0)
