from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from application.usage import TokenUsage


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: MessageRole
    content: str


class FinishReason(StrEnum):
    STOP = "stop"
    LENGTH = "length"
    CONTENT_FILTER = "content_filter"
    OTHER = "other"

    @classmethod
    def from_raw(cls, raw: str | None) -> "FinishReason":
        if not isinstance(raw, str):
            return cls.OTHER
        normalized: str = raw.strip().lower()
        known_reasons: dict[str, FinishReason] = {
            member.value: member
            for member in (cls.STOP, cls.LENGTH, cls.CONTENT_FILTER)
        }
        return known_reasons.get(normalized, cls.OTHER)


class CompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    messages: list[Message] = Field(min_length=1)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, gt=0)
    timeout_seconds: float = Field(default=180.0, gt=0)

    response_schema: dict[str, object] | None = None
    response_schema_name: str | None = None


class CompletionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    content: str
    finish_reason: FinishReason
    usage: TokenUsage
    latency_seconds: float = Field(default=0.0, ge=0.0)
