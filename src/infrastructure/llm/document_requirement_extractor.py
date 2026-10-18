"""LLM adapter for document requirement extraction."""
import json
from typing import Any

import litellm

from application.requirements_extraction import ExtractionChunk
from config.root import AppSettings


class LlmDocumentRequirementExtractor:
    """Extract a single document fragment using the configured LLM endpoint."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def extract(self, text: str, source_name: str) -> ExtractionChunk:
        prompt = (
            "Extract only requirements explicitly supported by the source. "
            "Do not invent missing facts. Preserve exact evidence excerpts. "
            "Return JSON with keys requirements (objects with statement, kind, "
            "source_excerpt, optional source_location), is_relevant, "
            "ambiguity_notes, and conflict_notes. kind must be functional or "
            "non_functional. If the source is unrelated to system design, set "
            "is_relevant=false and return no requirements.\n"
            f"Source name: {source_name}\n<document>\n{text}\n</document>"
        )
        response: Any = litellm.completion(
            model=self._settings.llm.model,
            api_base=self._settings.base_url,
            api_key=self._settings.api_key.get_secret_value(),
            messages=[
                {"role": "system", "content": "You are a precise requirements analyst. Output valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=min(self._settings.llm.max_tokens, 8_000),
            timeout=self._settings.llm.timeout_seconds,
            response_format={"type": "json_object"},
            num_retries=0,
        )
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise ValueError("LLM returned an empty extraction response")
        return ExtractionChunk.model_validate(json.loads(content))
