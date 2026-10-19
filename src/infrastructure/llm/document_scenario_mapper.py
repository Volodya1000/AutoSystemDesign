"""LLM adapter for mapping verified claims to scenario-shaped candidates."""

from config.root import AppSettings
from domain.document_requirements import DocumentRequirements
from domain.scenario_extraction import DocumentScenarioExtraction
from infrastructure.llm.client import LiteLlmClient
from infrastructure.llm.models import Message, MessageRole
from infrastructure.llm.prompts.document_scenario import (
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)
from infrastructure.llm.protocols import CompletionClient
from infrastructure.llm.structured_output import (
    complete_structured_response,
    encode_prompt_data,
)


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
        response_content = complete_structured_response(
            settings=self._settings,
            client=self._client,
            messages=[
                Message(role=MessageRole.SYSTEM, content=SYSTEM_PROMPT),
                Message(
                    role=MessageRole.USER,
                    content=USER_PROMPT_TEMPLATE.format(
                        requirements_json=encode_prompt_data(verified_claims)
                    ),
                ),
            ],
            response_schema=DocumentScenarioExtraction.model_json_schema(),
            response_schema_name="document_scenario_extraction",
            operation="scenario mapping",
        )
        return DocumentScenarioExtraction.model_validate_json(response_content)
