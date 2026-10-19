"""LLM agent implementing the ApiDesigner port."""

from __future__ import annotations

import logging

from application.tasks import ApiDesignProposal, ApiDesignTask, DesignTaskMode
from config.root import AppSettings
from domain.models.api import ApiDesign
from infrastructure.design.api_parser import parse_api_design
from infrastructure.llm.models import CompletionRequest, CompletionResult
from infrastructure.llm.protocols import CompletionClient
from infrastructure.prompts.api_generation import (
    build_api_initial_messages,
    build_api_repair_messages,
)


class ApiDesignerAgent:
    def __init__(self, client: CompletionClient, settings: AppSettings) -> None:
        self._client: CompletionClient = client
        self._settings: AppSettings = settings
        self.logger: logging.Logger = logging.getLogger(self.__class__.__name__)

    def propose(self, task: ApiDesignTask) -> ApiDesignProposal:
        if task.mode is DesignTaskMode.INITIAL:
            messages = build_api_initial_messages(task)
        else:
            messages = build_api_repair_messages(task)

        request = CompletionRequest(
            messages=messages,
            temperature=self._settings.llm.temperature,
            max_tokens=self._settings.llm.max_tokens,
            timeout_seconds=self._settings.llm.timeout_seconds,
            response_schema=ApiDesign.model_json_schema(),
            response_schema_name="api_design",
        )

        completion: CompletionResult = self._client.complete(request)
        self.logger.debug("Raw API LLM output:\n%s", completion.content)

        api_design: ApiDesign = parse_api_design(
            completion.content, usage=completion.usage
        )
        return ApiDesignProposal(
            payload=api_design,
            raw_content=completion.content,
            usage=completion.usage,
            latency_seconds=completion.latency_seconds,
        )
