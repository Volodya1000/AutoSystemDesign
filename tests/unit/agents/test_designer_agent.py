# Copyright (c) 2026 Volodya1000
"""Unit tests of the ArchitectureDesignerAgent on a fake LLM client."""

import pytest
from pydantic import SecretStr

from application.exceptions.generation_exceptions import DesignProposalParsingError
from application.tasks import DesignProposal, DesignTask, DesignTaskMode
from application.usage import TokenUsage
from config.llm import LlmSettings, StructuredOutputMode
from config.root import AppSettings
from domain.models import DesignScenario
from infrastructure.agents.designer import ArchitectureDesignerAgent
from infrastructure.exceptions.llm_exceptions import LlmConnectionError
from infrastructure.llm.models import (
    CompletionRequest,
    CompletionResult,
    FinishReason,
)
from infrastructure.prompts.fragments_schema import FEW_SHOT_GRAPH_JSON

pytestmark = pytest.mark.unit


@pytest.fixture(name="settings")
def _settings_fixture() -> AppSettings:
    return AppSettings(
        base_url="http://localhost:1234/v1",
        api_key=SecretStr("fake"),
        llm=LlmSettings(
            model="lm_studio/fake",
            temperature=0.7,
            max_tokens=512,
            timeout_seconds=12.5,
            structured_output_mode=StructuredOutputMode.PROMPT,
        ),
    )


class FakeLlmClient:
    """Test double: records requests, replays a scripted completion."""

    def __init__(self, content: str) -> None:
        self._content = content
        self.received_requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> CompletionResult:
        self.received_requests.append(request)
        return CompletionResult(
            model="fake-model",
            content=self._content,
            finish_reason=FinishReason.STOP,
            usage=TokenUsage(prompt_tokens=11, completion_tokens=7),
            latency_seconds=0.01,
        )


class RaisingLlmClient:
    """Test double that always raises a scripted infrastructure error."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    def complete(self, request: CompletionRequest) -> CompletionResult:
        del request
        raise self._error


_FENCED_CONTENT: str = "model reasoning\n```json\n" + FEW_SHOT_GRAPH_JSON + "\n```"


class TestArchitectureDesignerAgent:
    @staticmethod
    def test_propose_parses_fenced_output_with_think_block(
        scenario: DesignScenario, settings: AppSettings
    ) -> None:
        client: FakeLlmClient = FakeLlmClient(content=_FENCED_CONTENT)
        designer: ArchitectureDesignerAgent = ArchitectureDesignerAgent(
            client=client,
            settings=settings,
        )
        proposal: DesignProposal = designer.propose(
            DesignTask(scenario=scenario, mode=DesignTaskMode.INITIAL)
        )
        assert len(proposal.graph.nodes) == 4
        assert len(proposal.graph.edges) == 3
        assert proposal.raw_content == _FENCED_CONTENT
        assert proposal.usage.total_tokens == 18

    @staticmethod
    def test_propose_raises_parsing_error_on_garbage(
        scenario: DesignScenario, settings: AppSettings
    ) -> None:
        client: FakeLlmClient = FakeLlmClient(content="I cannot answer in JSON, sorry.")
        designer: ArchitectureDesignerAgent = ArchitectureDesignerAgent(
            client=client,
            settings=settings,
        )
        with pytest.raises(DesignProposalParsingError) as exc_info:
            designer.propose(DesignTask(scenario=scenario, mode=DesignTaskMode.INITIAL))
        assert exc_info.value.usage.total_tokens == 18
        assert exc_info.value.failure_details

    @staticmethod
    def test_propose_propagates_connection_errors(
        scenario: DesignScenario, settings: AppSettings
    ) -> None:
        connection_error: LlmConnectionError = LlmConnectionError(
            base_url="http://localhost:1234/v1",
            model="fake",
            original_message="boom",
        )
        designer: ArchitectureDesignerAgent = ArchitectureDesignerAgent(
            client=RaisingLlmClient(connection_error),
            settings=settings,
        )
        with pytest.raises(LlmConnectionError):
            designer.propose(DesignTask(scenario=scenario, mode=DesignTaskMode.INITIAL))

    @staticmethod
    def test_completion_request_carries_settings(
        scenario: DesignScenario, settings: AppSettings
    ) -> None:
        client: FakeLlmClient = FakeLlmClient(content=_FENCED_CONTENT)
        designer: ArchitectureDesignerAgent = ArchitectureDesignerAgent(
            client=client,
            settings=settings,
        )
        designer.propose(DesignTask(scenario=scenario, mode=DesignTaskMode.INITIAL))
        request: CompletionRequest = client.received_requests[0]
        assert request.temperature == 0.7
        assert request.max_tokens == 512
        assert request.timeout_seconds == 12.5
        assert request.messages
