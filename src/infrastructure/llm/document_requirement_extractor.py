"""LLM adapter for source-grounded document requirement extraction."""

from config.root import AppSettings
from domain.extraction_chunk import ExtractionChunk
from infrastructure.llm.client import LiteLlmClient
from infrastructure.llm.models import Message, MessageRole
from infrastructure.llm.prompts.document_requirements import (
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)
from infrastructure.llm.protocols import CompletionClient
from infrastructure.llm.structured_output import (
    complete_structured_response,
    encode_prompt_data,
)


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
        """Extract source-backed requirements from one text fragment."""
        response_content = complete_structured_response(
            settings=self._settings,
            client=self._client,
            messages=[
                Message(role=MessageRole.SYSTEM, content=SYSTEM_PROMPT),
                Message(
                    role=MessageRole.USER,
                    content=USER_PROMPT_TEMPLATE.format(
                        source_name_json=encode_prompt_data(source_name),
                        text_json=encode_prompt_data(text),
                    ),
                ),
            ],
            response_schema=ExtractionChunk.model_json_schema(),
            response_schema_name="document_requirements_extraction",
            operation="document requirement extraction",
        )
        return ExtractionChunk.model_validate_json(response_content)
