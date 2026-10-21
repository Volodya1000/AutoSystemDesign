# Copyright (c) 2026 Volodya1000
"""LLM adapter for source-grounded document requirement extraction."""

from domain.extraction_chunk import ExtractionChunk
from infrastructure.llm.prompts.document_requirements import (
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)
from infrastructure.llm.structured_output import (
    StructuredOutputAdapter,
    encode_prompt_data,
)


class LlmDocumentRequirementExtractor(StructuredOutputAdapter):
    """Extract one document fragment through the shared typed LLM client."""

    def extract(self, text: str, source_name: str) -> ExtractionChunk:
        """Extract source-backed requirements from one text fragment."""
        user_prompt = USER_PROMPT_TEMPLATE.format(
            source_name_json=encode_prompt_data(source_name),
            text_json=encode_prompt_data(text),
        )
        return self.complete_response(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_model=ExtractionChunk,
            response_schema_name="document_requirements_extraction",
            operation="document requirement extraction",
        )
