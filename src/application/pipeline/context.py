"""Read-only view passed to stages, plus the typed-payload accessor."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from application.pipeline.outcome import StageOutcome, StageStatus
from application.pipeline.ports import ArtifactWriter
from domain.models import DesignScenario


@dataclass(frozen=True)
class StageContext:
    scenario: DesignScenario
    out_dir: Path
    writer: ArtifactWriter
    upstream: Mapping[str, StageOutcome[object]]


class PipelineDependencyError(RuntimeError):
    """Raised when a stage's declared dependency is missing or ill-typed."""


def require_payload[PayloadT](
    context: StageContext,
    stage_name: str,
    expected_type: type[PayloadT],
) -> PayloadT:
    """Fetches a typed payload from an upstream stage's outcome.

    Runtime-checked via ``isinstance``. PARTIAL outcomes are acceptable:
    the payload was produced successfully, only optional artifacts failed.
    """
    outcome = context.upstream.get(stage_name)
    if outcome is None:
        raise PipelineDependencyError(f"Missing upstream stage '{stage_name}'")
    if outcome.status is StageStatus.FAILED:
        raise PipelineDependencyError(
            f"Upstream stage '{stage_name}' failed; cannot consume its payload"
        )
    payload = outcome.payload
    if not isinstance(payload, expected_type):
        raise PipelineDependencyError(
            f"Upstream stage '{stage_name}' payload is "
            f"{type(payload).__name__}, expected {expected_type.__name__}"
        )
    return payload
