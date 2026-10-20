"""Read-only view passed to stages, plus the typed-payload accessor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from application.pipeline.outcome import StageOutcome, StageStatus

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

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

    @classmethod
    def missing_upstream_stage(cls, stage_name: str) -> PipelineDependencyError:
        return cls(f"Missing upstream stage '{stage_name}'")

    @classmethod
    def failed_upstream_stage(cls, stage_name: str) -> PipelineDependencyError:
        return cls(f"Upstream stage '{stage_name}' failed; cannot consume its payload")

    @classmethod
    def unexpected_payload_type(
        cls, stage_name: str, actual_type: str, expected_type: str
    ) -> PipelineDependencyError:
        return cls(
            f"Upstream stage '{stage_name}' payload is {actual_type}, "
            f"expected {expected_type}"
        )


def require_payload[PayloadT](
    context: StageContext,
    stage_name: str,
    expected_type: type[PayloadT],
) -> PayloadT:
    """Fetch a typed payload from an upstream stage's outcome.

    Runtime-checked via ``isinstance``. PARTIAL outcomes are acceptable:
    the payload was produced successfully, only optional artifacts failed.
    """
    outcome = context.upstream.get(stage_name)
    if outcome is None:
        raise PipelineDependencyError.missing_upstream_stage(stage_name)
    if outcome.status is StageStatus.FAILED:
        raise PipelineDependencyError.failed_upstream_stage(stage_name)
    payload = outcome.payload
    if not isinstance(payload, expected_type):
        raise PipelineDependencyError.unexpected_payload_type(
            stage_name, type(payload).__name__, expected_type.__name__
        )
    return payload
