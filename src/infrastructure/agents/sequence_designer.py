import logging

from application.tasks import (
    DesignTaskMode,
    SequenceContextProposal,
    SequenceContextTask,
    SequenceInteractionProposal,
    SequenceInteractionTask,
)
from config.root import AppSettings
from domain.models.sequence import InteractionScenario
from domain.models.system_design import SystemContextOutput
from infrastructure.design.sequence_parser import (
    extract_json_payload,
    parse_interaction_scenario,
    parse_system_context,
)
from infrastructure.llm.models import CompletionRequest
from infrastructure.prompts.sequence_generation import (
    build_context_initial_messages,
    build_context_repair_messages,
    build_interaction_initial_messages,
    build_interaction_repair_messages,
)


class SequenceDesignerAgent:
    def __init__(self, client, settings: AppSettings) -> None:
        self._client = client
        self._settings = settings
        self.logger = logging.getLogger(self.__class__.__name__)

    def propose_context(self, task: SequenceContextTask) -> SequenceContextProposal:
        if task.mode is DesignTaskMode.INITIAL:
            messages = build_context_initial_messages(task)
        else:
            messages = build_context_repair_messages(task)

        request = CompletionRequest(
            messages=messages,
            temperature=self._settings.llm.temperature,
            max_tokens=self._settings.llm.max_tokens,
            timeout_seconds=self._settings.llm.timeout_seconds,
            response_schema=SystemContextOutput.model_json_schema(),
            response_schema_name="system_context_output",
        )

        completion = self._client.complete(request)
        self.logger.debug("Raw Context LLM output:\n%s", completion.content)

        payload = extract_json_payload(completion.content)
        context_output = parse_system_context(payload, usage=completion.usage)

        return SequenceContextProposal(
            context_output=context_output,
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

        payload = extract_json_payload(completion.content)
        scenario_output = parse_interaction_scenario(payload, usage=completion.usage)

        return SequenceInteractionProposal(
            interaction_scenario=scenario_output,
            raw_content=completion.content,
            usage=completion.usage,
            latency_seconds=completion.latency_seconds,
        )
