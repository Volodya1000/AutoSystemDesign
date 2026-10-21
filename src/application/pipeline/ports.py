"""Application-level ports; concrete implementations live in infrastructure."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from application.pipeline.outcome import DiagramRenderResult, StageOutcome
    from application.results import GenerationAttempt
    from application.usage import TokenUsage
    from domain.models.api import ApiDesign


class ArtifactWriter(Protocol):
    """Persists textual artifacts (JSON ASTs, catalogs, etc.)."""

    def write_text(self, path: Path, content: str) -> Path: ...


class DiagramRenderer[SubjectT](Protocol):
    """Renders a diagram for a domain subject, best-effort.

    Implementations return warnings rather than raising for expected
    visualization errors (rendering/saving failures, unavailable servers).
    Unexpected programming errors are not swallowed.
    """

    def render(
        self,
        subject: SubjectT,
        *,
        title: str,
        base_name: str,
        out_dir: Path,
    ) -> DiagramRenderResult: ...


class GenerationReporter(Protocol):
    """Per-stage reporting of attempts and token usage."""

    def attempts[PayloadT](
        self, attempts: Sequence[GenerationAttempt[PayloadT]], label: str
    ) -> None: ...

    def tokens(self, usage: TokenUsage, generation_seconds: float) -> None: ...


class PipelineReporter(Protocol):
    """Reports the final outcome of a pipeline run."""

    def report(self, outcomes: Sequence[StageOutcome[object]]) -> None: ...


class ApiArtifactRenderer(Protocol):
    """Renders OpenAPI specification and interactive documentation."""

    def render(
        self,
        subject: ApiDesign,
        *,
        title: str,
        base_name: str,
        out_dir: Path,
    ) -> DiagramRenderResult: ...
