# Copyright (c) 2026 Volodya1000
"""Token accounting shared across layers."""

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field


class TokenUsage(BaseModel):
    """Token accounting for a single LLM completion."""

    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    estimated: bool = False

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @classmethod
    def aggregate(cls, usages: Iterable["TokenUsage"]) -> "TokenUsage":
        """Sum token counts over multiple completions."""
        usage_list: list[TokenUsage] = list(usages)
        return cls(
            prompt_tokens=sum(usage.prompt_tokens for usage in usage_list),
            completion_tokens=sum(usage.completion_tokens for usage in usage_list),
            estimated=any(usage.estimated for usage in usage_list),
        )
