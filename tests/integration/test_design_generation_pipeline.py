import logging

import pytest

from application.results import GenerationStatus
from application.services.design_generation_service import DesignGenerationService
from application.usage import TokenUsage
from config.root import AppSettings
from domain.models import DesignScenario
from domain.specifications.structural_validator import StructuralTopologyValidator
from infrastructure.agents.designer import ArchitectureDesignerAgent
from infrastructure.llm.client import LiteLlmClient

pytestmark = pytest.mark.integration

_logger: logging.Logger = logging.getLogger(__name__)


def test_end_to_end(
    gate_settings: AppSettings,
    app_settings: AppSettings,
    scenario: DesignScenario,
    require_lm_studio: None,
) -> None:
    """Full pipeline with the repair loop, wired manually (temperature 0.0)."""
    designer: ArchitectureDesignerAgent = ArchitectureDesignerAgent(
        client=LiteLlmClient(settings=gate_settings), settings=gate_settings
    )
    service: DesignGenerationService = DesignGenerationService(
        designer=designer,
        validators=[StructuralTopologyValidator()],
        max_attempts=app_settings.generation.max_attempts,
    )
    result = service.generate(scenario)

    _logger.info(
        "e2e: status=%s attempts=%d tokens=%d",
        result.status.value,
        len(result.attempts),
        result.total_usage.total_tokens,
    )

    assert result.status is GenerationStatus.SUCCEEDED
    assert result.graph is not None
    assert StructuralTopologyValidator().validate(result.graph).is_successful
    assert result.total_usage.prompt_tokens == sum(
        attempt.usage.prompt_tokens for attempt in result.attempts
    )
    assert result.total_usage.completion_tokens == sum(
        attempt.usage.completion_tokens for attempt in result.attempts
    )
    expected_usage: TokenUsage = TokenUsage.aggregate(
        attempt.usage for attempt in result.attempts
    )
    assert result.total_usage == expected_usage
    for attempt in result.attempts:
        assert attempt.usage.total_tokens > 0
