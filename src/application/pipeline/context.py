"""Read-only view passed to stages, plus the typed-payload accessor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from application.pipeline.outcome import StageOutcome, StageStatus

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from application.pipeline.protocols import ArtifactWriterProtocol
    from application.pipeline.stage import StageId
    from domain.models import DesignScenario


@dataclass(frozen=True)
class StageContext:
    scenario: DesignScenario
    out_dir: Path
    writer: ArtifactWriterProtocol
    upstream: Mapping[StageId, StageOutcome[object]]


class PipelineDependencyError(RuntimeError):
    """Raised when a stage's declared dependency is missing or ill-typed."""

    @classmethod
    def missing_upstream_stage(cls, stage_id: StageId) -> PipelineDependencyError:
        return cls(f"Missing upstream stage '{stage_id}'")

    @classmethod
    def failed_upstream_stage(cls, stage_id: StageId) -> PipelineDependencyError:
        return cls(f"Upstream stage '{stage_id}' failed; cannot consume its payload")

    @classmethod
    def unexpected_payload_type(
        cls, stage_id: StageId, actual_type: str, expected_type: str
    ) -> PipelineDependencyError:
        return cls(
            f"Upstream stage '{stage_id}' payload is {actual_type}, "
            f"expected {expected_type}"
        )


def require_payload[PayloadT](
    context: StageContext,
    stage_id: StageId,
    expected_type: type[PayloadT],
) -> PayloadT:
    """Fetch a typed payload from an upstream stage's outcome.

    Runtime-checked via ``isinstance``. PARTIAL outcomes are acceptable:
    the payload was produced successfully, only optional artifacts failed.
    """
    outcome = context.upstream.get(stage_id)
    if outcome is None:
        raise PipelineDependencyError.missing_upstream_stage(stage_id)
    if outcome.status is StageStatus.FAILED:
        raise PipelineDependencyError.failed_upstream_stage(stage_id)
    payload = outcome.payload
    if not isinstance(payload, expected_type):
        raise PipelineDependencyError.unexpected_payload_type(
            stage_id, type(payload).__name__, expected_type.__name__
        )
    return payload
