"""Unit tests of the stage builders in the composition root.

These exercise the wiring without any LLM: ``_build_*_stage`` accepts an
explicit ``AppSettings``, so no environment variables or real endpoint
are required.
"""

import pytest
from pydantic import SecretStr

from application.pipeline.stages.api import ApiStage
from application.pipeline.stages.c4 import C4Stage
from application.pipeline.stages.sequence import SequenceStage
from config.llm import LlmSettings, StructuredOutputMode
from config.root import AppSettings
from infrastructure.composition import (
    _build_api_stage,
    _build_c4_stage,
    _build_sequence_stage,
)
from infrastructure.reporting import LoggingGenerationReporter

pytestmark = pytest.mark.unit


def _settings() -> AppSettings:
    return AppSettings(
        base_url="http://localhost:1234/v1",
        api_key=SecretStr("fake"),
        llm=LlmSettings(
            model="lm_studio/fake",
            temperature=0.0,
            max_tokens=64,
            timeout_seconds=5.0,
            structured_output_mode=StructuredOutputMode.PROMPT,
        ),
    )


def test_build_c4_stage_without_renderer() -> None:
    stage = _build_c4_stage(
        _settings(), renderer=None, reporter=LoggingGenerationReporter()
    )
    assert isinstance(stage, C4Stage)
    assert stage.name == "c4"
    assert not stage.depends_on


def test_build_sequence_stage_depends_on_c4() -> None:
    stage = _build_sequence_stage(
        _settings(), renderer=None, reporter=LoggingGenerationReporter()
    )
    assert isinstance(stage, SequenceStage)
    assert stage.name == "sequence"
    assert stage.depends_on == ("c4",)


def test_build_api_stage_depends_on_c4_and_sequence() -> None:
    stage = _build_api_stage(_settings(), reporter=LoggingGenerationReporter())
    assert isinstance(stage, ApiStage)
    assert stage.name == "api"
    assert stage.depends_on == ("c4", "sequence")
