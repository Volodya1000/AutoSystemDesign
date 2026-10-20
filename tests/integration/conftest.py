"""Pytest fixtures for integration tests that call a real LLM."""

import httpx
import pytest
from pydantic import ValidationError

from application.tasks import DesignTask, DesignTaskMode
from config.root import (
    CONFIG_FILE_ENV_VAR,
    AppSettings,
    load_app_settings,
    with_llm_updates,
)
from config.testing import IntegrationSettings
from domain.models import DesignScenario
from domain.specifications.structural_validator import StructuralTopologyValidator
from infrastructure.agents.designer import ArchitectureDesignerAgent
from infrastructure.llm.client import LiteLlmClient

_TEST_CONFIG_FILE: str = "config.test.yaml"


@pytest.fixture(scope="session")
def app_settings() -> AppSettings:
    """Load test settings (config.test.yaml + .env); skips when unset."""
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setenv(CONFIG_FILE_ENV_VAR, _TEST_CONFIG_FILE)
        try:
            return load_app_settings()
        except ValidationError as error:
            pytest.skip(f"Settings are not configured (.env / ASD_* env vars): {error}")


@pytest.fixture(scope="session")
def gate_settings(app_settings: AppSettings) -> AppSettings:
    """Temperature pinned to 0.0 for deterministic capability gating."""
    return with_llm_updates(app_settings, temperature=0.0)


@pytest.fixture(scope="session")
def require_lm_studio(app_settings: AppSettings) -> None:
    """Skips tests when the LM Studio endpoint is not reachable."""
    try:
        response: httpx.Response = httpx.get(
            f"{app_settings.base_url}/models", timeout=3.0
        )
    except httpx.HTTPError as error:
        pytest.skip(f"LM Studio is not reachable at {app_settings.base_url}: {error}")
    if response.status_code != EXPECTED_IF_RESPONSE_STATUS_CODE:
        pytest.skip(
            f"LM Studio responded with {response.status_code} "
            f"at {app_settings.base_url}"
        )


@pytest.fixture(scope="session")
def integration_test_settings(app_settings: AppSettings) -> IntegrationSettings:
    """Exposes the testing section of the test settings."""
    return app_settings.testing


@pytest.fixture(scope="session")
def structural_validator() -> StructuralTopologyValidator:
    """Shared structural validator instance."""
    return StructuralTopologyValidator()


@pytest.fixture(scope="session")
def designer(gate_settings: AppSettings) -> ArchitectureDesignerAgent:
    """Real designer wired to the real LLM client."""
    return ArchitectureDesignerAgent(
        client=LiteLlmClient(settings=gate_settings), settings=gate_settings
    )


@pytest.fixture
def initial_task(scenario: DesignScenario) -> DesignTask:
    """Create the initial design task for the shared scenario."""
    return DesignTask(scenario=scenario, mode=DesignTaskMode.INITIAL)

EXPECTED_IF_RESPONSE_STATUS_CODE = 200

