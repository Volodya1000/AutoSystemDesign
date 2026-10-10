"""M1 capability gate: single-shot structured output over a real LLM."""

import logging

import pytest

from application.exceptions.generation_exceptions import DesignProposalParsingError
from application.tasks import DesignProposal, DesignTask, DesignTaskMode
from config.llm import StructuredOutputMode
from config.root import AppSettings, with_llm_updates
from config.testing import IntegrationSettings
from domain.models import DesignScenario
from domain.specifications.interfaces import ValidationResult
from domain.specifications.structural_validator import StructuralTopologyValidator
from infrastructure.agents.designer import ArchitectureDesignerAgent
from infrastructure.exceptions.llm_exceptions import LlmConnectionError
from infrastructure.llm.client import LiteLlmClient

pytestmark = pytest.mark.integration

_logger: logging.Logger = logging.getLogger(__name__)

MINIMUM_NODE_COUNT: int = 3


def test_single_shot_structured_output_capability(
    designer: ArchitectureDesignerAgent,
    structural_validator: StructuralTopologyValidator,
    initial_task: DesignTask,
    require_lm_studio: None,
    integration_test_settings: IntegrationSettings,
) -> None:
    """Every single-shot run must parse and pass structural validation."""
    successes: int = 0
    failures: list[str] = []
    token_totals: list[int] = []

    for _ in range(integration_test_settings.generation_runs):
        try:
            proposal: DesignProposal = designer.propose(initial_task)
        except DesignProposalParsingError as error:
            token_totals.append(error.usage.total_tokens)
            failures.append(
                "parsing failure: "
                f"{[detail.error_type for detail in error.failure_details]}"
            )
            continue
        token_totals.append(proposal.usage.total_tokens)
        validation: ValidationResult = structural_validator.validate(proposal.graph)
        if not validation.is_successful:
            failures.append(
                "structural validation failed: "
                + "; ".join(error.error_code for error in validation.errors)
            )
            continue
        if len(proposal.graph.nodes) < MINIMUM_NODE_COUNT:
            failures.append(f"graph too small: {len(proposal.graph.nodes)} nodes")
            continue
        if proposal.usage.total_tokens <= 0:
            failures.append("token usage was not reported")
            continue
        successes += 1

    rate: float = successes / integration_test_settings.generation_runs
    _logger.info(
        "capability gate: runs=%d successes=%d rate=%.2f min_required=%.2f tokens=%s",
        integration_test_settings.generation_runs,
        successes,
        rate,
        integration_test_settings.min_single_shot_success_rate,
        token_totals,
    )
    assert rate >= integration_test_settings.min_single_shot_success_rate, (
        f"M1 capability gate failed. Failures: {failures}"
    )


def test_json_schema_mode_probe(
    app_settings: AppSettings,
    scenario: DesignScenario,
    require_lm_studio: None,
) -> None:
    """Non-strict probe: documents JSON_SCHEMA support of this endpoint."""
    settings: AppSettings = with_llm_updates(
        app_settings,
        temperature=0.0,
        structured_output_mode=StructuredOutputMode.JSON_SCHEMA,
    )
    probe_designer: ArchitectureDesignerAgent = ArchitectureDesignerAgent(
        client=LiteLlmClient(settings=settings), settings=settings
    )
    task: DesignTask = DesignTask(scenario=scenario, mode=DesignTaskMode.INITIAL)
    try:
        proposal: DesignProposal = probe_designer.propose(task)
    except (LlmConnectionError, DesignProposalParsingError):
        pytest.xfail("JSON_SCHEMA structured output is not supported by this endpoint")
    validation: ValidationResult = StructuralTopologyValidator().validate(
        proposal.graph
    )
    assert validation.is_successful
