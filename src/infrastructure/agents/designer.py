"""LLM-backed implementation of the ArchitectureDesigner port."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from application.tasks import DesignProposal, DesignTask, DesignTaskMode
from config.root import AppSettings
from domain.models.topology import ArchitectureGraph
from infrastructure.design.parser import extract_json_payload, parse_architecture_graph
from infrastructure.llm.models import CompletionRequest, CompletionResult, Message
from infrastructure.prompts.design_generation import build_initial_messages
from infrastructure.prompts.design_repair import build_repair_messages

if TYPE_CHECKING:
    from infrastructure.llm.client import LiteLlmClient


class ArchitectureDesignerAgent:
    """Adapter over the LLM transport implementing the ArchitectureDesigner port.

    Deliberately thin (SRP): selects the prompt strategy, applies sampling
    settings, delegates transport to the client and parsing to the parser.
    Infrastructure errors are not caught here.
    """

    def __init__(self, client: LiteLlmClient, settings: AppSettings) -> None:
        self._client = client
        self._settings = settings
        self.logger: logging.Logger = logging.getLogger(self.__class__.__name__)

    def propose(self, task: DesignTask) -> DesignProposal:
        if task.mode is DesignTaskMode.INITIAL:
            messages: list[Message] = build_initial_messages(task)
        else:
            messages = build_repair_messages(task)

        request: CompletionRequest = CompletionRequest(
            messages=messages,
            temperature=self._settings.llm.temperature,
            max_tokens=self._settings.llm.max_tokens,
            timeout_seconds=self._settings.llm.timeout_seconds,
        )
        completion: CompletionResult = self._client.complete(request)
        self.logger.debug("Raw LLM output:\n%s", completion.content)

        payload: str = extract_json_payload(completion.content)
        graph: ArchitectureGraph = parse_architecture_graph(
            payload, usage=completion.usage
        )
        return DesignProposal(
            graph=graph,
            raw_content=completion.content,
            usage=completion.usage,
        )
