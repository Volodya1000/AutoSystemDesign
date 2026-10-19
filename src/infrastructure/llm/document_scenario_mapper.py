"""LLM adapter for mapping verified claims to scenario-shaped candidates."""

import json

from config.root import AppSettings
from domain.document_requirements import DocumentRequirements
from domain.scenario_extraction import DocumentScenarioExtraction
from infrastructure.llm.client import LiteLlmClient
from infrastructure.llm.models import (
    CompletionRequest,
    CompletionResult,
    FinishReason,
    Message,
    MessageRole,
)
from infrastructure.llm.prompts.document_scenario import (
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)
from infrastructure.llm.protocols import CompletionClient


class LlmDocumentScenarioMapper:
    """Map previously verified requirement claims into evidence-bearing DTOs."""

    def __init__(
        self,
        settings: AppSettings,
        client: CompletionClient | None = None,
    ) -> None:
        self._settings = settings
        self._client: CompletionClient = client or LiteLlmClient(settings)

    def map(self, requirements: DocumentRequirements) -> DocumentScenarioExtraction:
        """Create typed scenario candidates without admitting unverified citations."""
        verified_claims = {
            "requirements": [
                requirement.model_dump(mode="json")
                for requirement in requirements.requirements
            ]
        }
        encoded_requirements = json.dumps(verified_claims, ensure_ascii=False)
        encoded_requirements = encoded_requirements.replace("<", "\\u003c").replace(
            ">", "\\u003e"
        )
        request = CompletionRequest(
            messages=[
                Message(role=MessageRole.SYSTEM, content=SYSTEM_PROMPT),
                Message(
                    role=MessageRole.USER,
                    content=USER_PROMPT_TEMPLATE.format(
                        requirements_json=encoded_requirements
                    ),
                ),
            ],
            temperature=0.0,
            max_tokens=min(self._settings.llm.max_tokens, 8_000),
            timeout_seconds=self._settings.llm.timeout_seconds,
            response_schema=DocumentScenarioExtraction.model_json_schema(),
            response_schema_name="document_scenario_extraction",
        )
        response: CompletionResult = self._client.complete(request)
        if response.finish_reason is FinishReason.LENGTH:
            raise ValueError(
                "LLM scenario mapping was truncated; reduce the number of verified "
                "requirements or increase the configured token limit."
            )
        if response.finish_reason is FinishReason.CONTENT_FILTER:
            raise ValueError("LLM scenario mapping was blocked by the content filter")
        if not response.content.strip():
            raise ValueError("LLM returned an empty scenario mapping")
        return DocumentScenarioExtraction.model_validate_json(response.content)
