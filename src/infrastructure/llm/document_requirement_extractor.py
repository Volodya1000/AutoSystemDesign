"""LLM adapter for source-grounded document requirement extraction."""

import json

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
from infrastructure.llm.protocols import CompletionClient


class LlmDocumentRequirementExtractor:
    """Extract one document fragment through the shared typed LLM client."""

    def __init__(
        self,
        settings: AppSettings,
        client: CompletionClient | None = None,
    ) -> None:
        self._settings = settings
        self._client: CompletionClient = client or LiteLlmClient(settings)

    def extract(self, text: str, source_name: str) -> ExtractionChunk:
        encoded_text = json.dumps(text, ensure_ascii=False)
        # Prevent document content from breaking the prompt's data boundary.
        encoded_text = encoded_text.replace("<", "\\u003c").replace(">", "\\u003e")
        encoded_source_name = json.dumps(source_name, ensure_ascii=False)
        encoded_source_name = encoded_source_name.replace("<", "\\u003c").replace(
            ">", "\\u003e"
        )
        request = CompletionRequest(
            messages=[
                Message(role=MessageRole.SYSTEM, content=SYSTEM_PROMPT),
                Message(
                    role=MessageRole.USER,
                    content=USER_PROMPT_TEMPLATE.format(
                        source_name_json=encoded_source_name,
                        text_json=encoded_text,
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
        if response.finish_reason is FinishReason.CONTENT_FILTER:
            raise ValueError(
                "LLM response was blocked by the provider's content filter"
            )
        if not response.content.strip():
            raise ValueError("LLM returned an empty extraction response")
        return ExtractionChunk.model_validate_json(response.content)
