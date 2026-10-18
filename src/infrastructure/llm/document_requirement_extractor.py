"""LLM adapter for document requirement extraction."""

from application.usage import TokenUsage
from config.root import AppSettings
from domain.extraction_chunk import ExtractionChunk
from infrastructure.llm.client import LiteLlmClient
from infrastructure.llm.models import (
    CompletionRequest,
    CompletionResult,
    FinishReason,
    Message,
    MessageRole,
)
from infrastructure.llm.prompts.document_requirements import (
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)


class LlmDocumentRequirementExtractor:
    """Extract one document fragment through the shared typed LLM client."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._client = LiteLlmClient(settings)

    def extract(self, text: str, source_name: str) -> ExtractionChunk:
        request = CompletionRequest(
            messages=[
                Message(role=MessageRole.SYSTEM, content=SYSTEM_PROMPT),
                Message(
                    role=MessageRole.USER,
                    content=USER_PROMPT_TEMPLATE.format(
                        source_name=source_name,
                        text=text,
                    ),
                ),
            ],
            temperature=0.0,
            max_tokens=min(self._settings.llm.max_tokens, 8_000),
            timeout_seconds=self._settings.llm.timeout_seconds,
            response_schema=ExtractionChunk.model_json_schema(),
            response_schema_name="document_requirements_extraction",
        )
        response: CompletionResult = self._client.complete(request)
        if response.finish_reason is FinishReason.LENGTH:
            raise ValueError(
                "LLM response was truncated; reduce document fragment size "
                "or increase the configured token limit."
            )
        if not response.content.strip():
            raise ValueError("LLM returned an empty extraction response")
        return ExtractionChunk.model_validate_json(response.content)
