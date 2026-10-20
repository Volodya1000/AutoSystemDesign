"""Unit tests for the LLM-backed designer adapters."""

import pytest
from pydantic import SecretStr

import infrastructure.agents.api_designer as api_designer_module
import infrastructure.agents.designer as architecture_designer_module
import infrastructure.agents.sequence_designer as sequence_designer_module
from application.tasks import (
    ApiDesignTask,
    DesignTask,
    DesignTaskMode,
    SequenceInteractionTask,
    SequenceRoleTask,
)
from application.usage import TokenUsage
from config.llm import LlmSettings, StructuredOutputMode
from config.root import AppSettings
from domain.models.api import (
    ApiDesign,
    ApiOperation,
    ApiResponse,
    HttpMethod,
)
from domain.models.ast_steps import MessageStep
from domain.models.functional import FunctionalRequirement
from domain.models.roles import BusinessRole, ProjectRolesCatalog
from domain.models.scenarios import DesignScenario
from domain.models.sequence import (
    ComponentLifeline,
    InteractionScenario,
    UserLifeline,
)
from domain.models.topology import ArchitectureGraph
from infrastructure.llm.models import (
    CompletionRequest,
    CompletionResult,
    FinishReason,
    Message,
    MessageRole,
)

from tests.unit.constants import EXPECTED_REQUEST_MAX_TOKENS

EXPECTED_ASSERT_PROPOSAL_LATENCY_SECONDS = 0.25
EXPECTED_ASSERT_REQUEST_TIMEOUT_SECONDS = 9.0
EXPECTED_ASSERT_REQUEST_TEMPERATURE = 0.3

pytestmark = pytest.mark.unit


class RecordingCompletionClient:
    """A transport fake that records requests and returns a stable response."""

    def __init__(self) -> None:
        self.requests: list[CompletionRequest] = []
        self.result = CompletionResult(
            model="test-model",
            content='{"generated": true}',
            finish_reason=FinishReason.STOP,
            usage=TokenUsage(prompt_tokens=7, completion_tokens=11),
            latency_seconds=0.25,
        )

    def complete(self, request: CompletionRequest) -> CompletionResult:
        self.requests.append(request)
        return self.result


def _settings() -> AppSettings:
    return AppSettings(
        base_url="http://localhost/v1",
        api_key=SecretStr("test-key"),
        llm=LlmSettings(
            model="test-model",
            temperature=0.3,
            max_tokens=512,
            timeout_seconds=9.0,
            structured_output_mode=StructuredOutputMode.JSON_SCHEMA,
        ),
    )


def _messages(content: str) -> list[Message]:
    return [Message(role=MessageRole.USER, content=content)]


def _install_prompt_builders(
    monkeypatch: pytest.MonkeyPatch,
    module: object,
    initial_name: str,
    repair_name: str,
) -> None:
    monkeypatch.setattr(
        module,
        initial_name,
        lambda _task: _messages("initial prompt"),
    )
    monkeypatch.setattr(
        module,
        repair_name,
        lambda _task: _messages("repair prompt"),
    )


def _scenario() -> DesignScenario:
    requirement = FunctionalRequirement(
        identifier="FR-1",
        name="Create resource",
        text="A user creates a resource.",
    )
    return DesignScenario(
        identifier="agent_test",
        description="Designer agent test",
        functional_requirements=[requirement],
    )


def _requirement() -> FunctionalRequirement:
    return FunctionalRequirement(
        identifier="FR-1",
        name="Create resource",
        text="A user creates a resource.",
    )


def _graph() -> ArchitectureGraph:
    return ArchitectureGraph(nodes=[], edges=[])


def _catalog() -> ProjectRolesCatalog:
    return ProjectRolesCatalog(
        roles=[
            BusinessRole(
                role_id="buyer",
                name="Buyer",
                description="User who initiates the request.",
            )
        ]
    )


def _api_design() -> ApiDesign:
    return ApiDesign(
        title="Test API",
        operations=[
            ApiOperation(
                operation_id="get_resources",
                method=HttpMethod.GET,
                path="/resources",
                summary="List resources",
                entrypoint_component_id="api",
                handler_component_id="api",
                requirement_ids=["FR-1"],
                responses=[ApiResponse(status_code="200", description="OK")],
            )
        ],
    )


def _interaction() -> InteractionScenario:
    return InteractionScenario(
        scenario_id="FR-1_scenario",
        requirement_identifier="FR-1",
        description="Create a resource",
        lifelines=[
            UserLifeline(
                kind="user",
                lifeline_id="buyer_1",
                business_role_id="buyer",
                scenario_role="initiator",
                description="The buyer initiating the request.",
            ),
            ComponentLifeline(
                kind="component",
                lifeline_id="api_1",
                architecture_node_id="api",
                display_name="API",
                description="Handles the request.",
            ),
        ],
        steps=[
            MessageStep(
                kind="message",
                from_lifeline="buyer_1",
                to_lifeline="api_1",
                action_name="POST /resources",
                message_kind="user_action",
                delivery_mode="sync",
            )
        ],
    )


@pytest.mark.parametrize("mode", [DesignTaskMode.INITIAL, DesignTaskMode.REPAIR])
def test_architecture_designer_builds_typed_request_and_parses_result(
    mode: DesignTaskMode,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = RecordingCompletionClient()
    graph = _graph()
    _install_prompt_builders(
        monkeypatch,
        architecture_designer_module,
        "build_initial_messages",
        "build_repair_messages",
    )
    monkeypatch.setattr(
        architecture_designer_module,
        "parse_architecture_graph",
        lambda _content, **_kwargs: graph,
    )

    task = DesignTask(scenario=_scenario(), mode=mode)
    proposal = architecture_designer_module.ArchitectureDesignerAgent(
        client, _settings()
    ).propose(task)

    request = client.requests[0]
    assert request.messages[0].content == (
        "initial prompt" if mode is DesignTaskMode.INITIAL else "repair prompt"
    )
    assert request.temperature == EXPECTED_ASSERT_REQUEST_TEMPERATURE
    assert request.max_tokens == EXPECTED_REQUEST_MAX_TOKENS
    assert request.timeout_seconds == EXPECTED_ASSERT_REQUEST_TIMEOUT_SECONDS
    assert request.response_schema == ArchitectureGraph.model_json_schema()
    assert request.response_schema_name == "architecture_graph"
    assert proposal.graph is graph
    assert proposal.raw_content == client.result.content
    assert proposal.usage == client.result.usage
    assert proposal.latency_seconds == EXPECTED_ASSERT_PROPOSAL_LATENCY_SECONDS


@pytest.mark.parametrize("mode", [DesignTaskMode.INITIAL, DesignTaskMode.REPAIR])
def test_api_designer_builds_typed_request_and_parses_result(
    mode: DesignTaskMode,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = RecordingCompletionClient()
    api_design = _api_design()
    _install_prompt_builders(
        monkeypatch,
        api_designer_module,
        "build_api_initial_messages",
        "build_api_repair_messages",
    )
    monkeypatch.setattr(
        api_designer_module,
        "parse_api_design",
        lambda _content, **_kwargs: api_design,
    )

    task = ApiDesignTask(
        scenario=_scenario(),
        architecture_graph=_graph(),
        sequence_scenarios=[],
        mode=mode,
    )
    proposal = api_designer_module.ApiDesignerAgent(client, _settings()).propose(task)

    request = client.requests[0]
    assert request.messages[0].content == (
        "initial prompt" if mode is DesignTaskMode.INITIAL else "repair prompt"
    )
    assert request.response_schema == ApiDesign.model_json_schema()
    assert request.response_schema_name == "api_design"
    assert request.temperature == EXPECTED_ASSERT_REQUEST_TEMPERATURE
    assert request.max_tokens == EXPECTED_ASSERT_REQUEST_MAX_TOKENS
    assert request.timeout_seconds == EXPECTED_ASSERT_REQUEST_TIMEOUT_SECONDS
    assert proposal.payload is api_design
    assert proposal.raw_content == client.result.content
    assert proposal.usage == client.result.usage
    assert proposal.latency_seconds == EXPECTED_ASSERT_PROPOSAL_LATENCY_SECONDS


@pytest.mark.parametrize("mode", [DesignTaskMode.INITIAL, DesignTaskMode.REPAIR])
def test_sequence_designer_builds_roles_request_and_parses_result(
    mode: DesignTaskMode,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = RecordingCompletionClient()
    catalog = _catalog()
    _install_prompt_builders(
        monkeypatch,
        sequence_designer_module,
        "build_roles_initial_messages",
        "build_roles_repair_messages",
    )
    monkeypatch.setattr(
        sequence_designer_module,
        "parse_roles_catalog",
        lambda _content, **_kwargs: catalog,
    )

    proposal = sequence_designer_module.SequenceDesignerAgent(
        client, _settings()
    ).propose_roles(SequenceRoleTask(scenario=_scenario(), mode=mode))

    request = client.requests[0]
    assert request.messages[0].content == (
        "initial prompt" if mode is DesignTaskMode.INITIAL else "repair prompt"
    )
    assert request.response_schema == ProjectRolesCatalog.model_json_schema()
    assert request.response_schema_name == "project_roles_catalog"
    assert proposal.payload is catalog
    assert proposal.raw_content == client.result.content
    assert proposal.usage == client.result.usage
    assert proposal.latency_seconds == EXPECTED_ASSERT_PROPOSAL_LATENCY_SECONDS


@pytest.mark.parametrize("mode", [DesignTaskMode.INITIAL, DesignTaskMode.REPAIR])
def test_sequence_designer_builds_interaction_request_and_parses_result(
    mode: DesignTaskMode,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = RecordingCompletionClient()
    interaction = _interaction()
    _install_prompt_builders(
        monkeypatch,
        sequence_designer_module,
        "build_interaction_initial_messages",
        "build_interaction_repair_messages",
    )
    monkeypatch.setattr(
        sequence_designer_module,
        "parse_interaction_scenario",
        lambda _content, **_kwargs: interaction,
    )

    task = SequenceInteractionTask(
        requirement=_requirement(),
        roles_catalog=_catalog(),
        architecture_graph=_graph(),
        mode=mode,
    )
    proposal = sequence_designer_module.SequenceDesignerAgent(
        client, _settings()
    ).propose_interaction(task)

    request = client.requests[0]
    assert request.messages[0].content == (
        "initial prompt" if mode is DesignTaskMode.INITIAL else "repair prompt"
    )
    assert request.response_schema == InteractionScenario.model_json_schema()
    assert request.response_schema_name == "interaction_scenario"
    assert proposal.payload is interaction
    assert proposal.raw_content == client.result.content
    assert proposal.usage == client.result.usage
    assert proposal.latency_seconds == EXPECTED_ASSERT_PROPOSAL_LATENCY_SECONDS

EXPECTED_ASSERT_REQUEST_MAX_TOKENS = 512
