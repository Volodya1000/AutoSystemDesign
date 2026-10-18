import logging

from application.tasks import (
    DesignTaskMode,
    SequenceInteractionProposal,
    SequenceInteractionTask,
    SequenceRoleProposal,
    SequenceRoleTask,
)
from config.root import AppSettings
from domain.models.roles import ProjectRolesCatalog
from domain.models.sequence import InteractionScenario
from infrastructure.design.sequence_parser import (
    parse_interaction_scenario,
    parse_roles_catalog,
)
from infrastructure.llm.models import CompletionRequest, CompletionResult
from infrastructure.llm.protocols import CompletionClient
from infrastructure.prompts.sequence_generation import (
    build_interaction_initial_messages,
    build_interaction_repair_messages,
    build_roles_initial_messages,
    build_roles_repair_messages,
)


class SequenceDesignerAgent:
    def __init__(self, client: CompletionClient, settings: AppSettings) -> None:
        self._client: CompletionClient = client
        self._settings: AppSettings = settings
        self.logger: logging.Logger = logging.getLogger(self.__class__.__name__)

    def propose_roles(self, task: SequenceRoleTask) -> SequenceRoleProposal:
        if task.mode is DesignTaskMode.INITIAL:
            messages = build_roles_initial_messages(task)
        else:
            messages = build_roles_repair_messages(task)

        request = CompletionRequest(
            messages=messages,
            temperature=self._settings.llm.temperature,
            max_tokens=self._settings.llm.max_tokens,
            timeout_seconds=self._settings.llm.timeout_seconds,
            response_schema=ProjectRolesCatalog.model_json_schema(),
            response_schema_name="project_roles_catalog",
        )

        completion: CompletionResult = self._client.complete(request)
        self.logger.debug("Raw Roles LLM output:\n%s", completion.content)

        catalog: ProjectRolesCatalog = parse_roles_catalog(\n            completion.content, usage=completion.usage\n        )
        return SequenceRoleProposal(
            payload=catalog,
            raw_content=completion.content,
            usage=completion.usage,
            latency_seconds=completion.latency_seconds,
        )

    def propose_interaction(
        self, task: SequenceInteractionTask
    ) -> SequenceInteractionProposal:
        if task.mode is DesignTaskMode.INITIAL:
            messages = build_interaction_initial_messages(task)
        else:
            messages = build_interaction_repair_messages(task)

        request = CompletionRequest(
            messages=messages,
            temperature=self._settings.llm.temperature,
            max_tokens=self._settings.llm.max_tokens,
            timeout_seconds=self._settings.llm.timeout_seconds,
            response_schema=InteractionScenario.model_json_schema(),
            response_schema_name="interaction_scenario",
        )

        completion = self._client.complete(request)
        self.logger.debug(
            "Raw Interaction LLM output for %s:\n%s",
            task.requirement.identifier,
            completion.content,
        )

        scenario = parse_interaction_scenario(
            completion.content, usage=completion.usage
        )
        return SequenceInteractionProposal(
            payload=scenario,
            raw_content=completion.content,
            usage=completion.usage,
            latency_seconds=completion.latency_seconds,
        )
