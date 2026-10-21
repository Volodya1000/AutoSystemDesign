"""LLM adapter for mapping verified claims to scenario-shaped candidates."""

from domain.document_requirements import DocumentRequirements
from domain.scenario_extraction import DocumentScenarioExtraction
from infrastructure.llm.prompts.document_scenario import (
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)
from infrastructure.llm.structured_output import (
    StructuredOutputAdapter,
    encode_prompt_data,
)


class LlmDocumentScenarioMapper(StructuredOutputAdapter):
    """Map previously verified requirement claims into evidence-bearing DTOs."""

    def map(self, requirements: DocumentRequirements) -> DocumentScenarioExtraction:
        """Create typed scenario candidates without admitting unverified citations."""
        verified_claims = {
            "requirements": [
                requirement.model_dump(mode="json")
                for requirement in requirements.requirements
            ]
        }
        user_prompt = USER_PROMPT_TEMPLATE.format(
            requirements_json=encode_prompt_data(verified_claims),
            response_schema_json=encode_prompt_data(
                DocumentScenarioExtraction.model_json_schema()
            ),
        )
        return self.complete_response(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_model=DocumentScenarioExtraction,
            response_schema_name="document_scenario_extraction",
            operation="scenario mapping",
        )
