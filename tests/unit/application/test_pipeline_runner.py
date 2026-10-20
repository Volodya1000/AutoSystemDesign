"""Contract tests for ordered pipeline execution and typed dependencies."""

from collections.abc import Sequence
from pathlib import Path
from types import MappingProxyType
from typing import cast

import pytest

from application.pipeline.context import (
    PipelineDependencyError,
    StageContext,
    require_payload,
)
from application.pipeline.outcome import StageOutcome, StageStatus
from application.pipeline.runner import PipelineRunner
from application.pipeline.stage import PipelineStage, StageId
from domain.models import DesignScenario
from tests.unit.in_memory_writer import InMemoryWriter

pytestmark = pytest.mark.unit


class RecordingReporter:
    def __init__(self) -> None:
        self.reports: list[tuple[StageOutcome[object], ...]] = []

    def report(self, outcomes: Sequence[StageOutcome[object]]) -> None:
        self.reports.append(tuple(outcomes))


class FakeStage:
    def __init__(
        self,
        name: StageId,
        status: StageStatus,
        *,
        depends_on: tuple[StageId, ...] = (),
        payload: object | None = None,
    ) -> None:
        self.name = name
        self.status = status
        self.depends_on = depends_on
        self.payload = payload
        self.contexts: list[StageContext] = []
        self.calls: int = 0

    def run(self, context: StageContext) -> StageOutcome[object]:
        self.calls += 1
        self.contexts.append(context)
        return StageOutcome(
            name=self.name,
            status=self.status,
            duration_seconds=0.1,
            total_tokens=3,
            payload=self.payload,
        )


def _scenario() -> DesignScenario:
    return DesignScenario(identifier="runner_test", description="Pipeline runner test")


def _run(
    stages: list[PipelineStage],
    reporter: RecordingReporter,
) -> int:
    return PipelineRunner(stages, reporter).run(
        _scenario(),
        Path("output"),
        InMemoryWriter(),
    )


def test_runner_rejects_empty_stage_list() -> None:
    with pytest.raises(ValueError, match="at least one stage"):
        PipelineRunner([], RecordingReporter())


@pytest.mark.parametrize(
    ("stages", "message"),
    [
        (
            [
                FakeStage(StageId.C4, StageStatus.SUCCEEDED),
                FakeStage(StageId.C4, StageStatus.SUCCEEDED),
            ],
            "Duplicate stage name",
        ),
        (
            [
                FakeStage(
                    StageId.SEQUENCE,
                    StageStatus.SUCCEEDED,
                    depends_on=(StageId.C4,),
                )
            ],
            "not scheduled before it",
        ),
        (
            [
                FakeStage(
                    StageId.SEQUENCE,
                    StageStatus.SUCCEEDED,
                    depends_on=(StageId.C4,),
                ),
                FakeStage(StageId.C4, StageStatus.SUCCEEDED),
            ],
            "not scheduled before it",
        ),
    ],
)
def test_runner_rejects_duplicate_or_out_of_order_stages(
    stages: list[PipelineStage],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        PipelineRunner(stages, RecordingReporter())


def test_runner_passes_immutable_snapshot_of_prior_stage_outcomes() -> None:
    c4 = FakeStage(StageId.C4, StageStatus.SUCCEEDED, payload={"architecture": True})
    sequence = FakeStage(
        StageId.SEQUENCE,
        StageStatus.PARTIAL,
        depends_on=(StageId.C4,),
        payload={"sequence": True},
    )
    reporter = RecordingReporter()

    exit_code = _run([c4, sequence], reporter)

    assert exit_code == 0
    assert c4.calls == 1
    assert sequence.calls == 1
    upstream = sequence.contexts[0].upstream
    assert isinstance(upstream, MappingProxyType)
    assert upstream[StageId.C4].payload == {"architecture": True}
    with pytest.raises(TypeError):
        cast("dict[StageId, StageOutcome[object]]", upstream)[
            StageId.API
        ] = upstream[StageId.C4]
    assert len(reporter.reports) == 1
    assert [outcome.name for outcome in reporter.reports[0]] == [
        StageId.C4,
        StageId.SEQUENCE,
    ]


def test_failed_stage_short_circuits_pipeline_and_reports_partial_history() -> None:
    c4 = FakeStage(StageId.C4, StageStatus.SUCCEEDED, payload={"architecture": True})
    sequence = FakeStage(StageId.SEQUENCE, StageStatus.FAILED, depends_on=(StageId.C4,))
    api = FakeStage(StageId.API, StageStatus.SUCCEEDED, depends_on=(StageId.SEQUENCE,))
    reporter = RecordingReporter()

    exit_code = _run([c4, sequence, api], reporter)

    assert exit_code == 1
    assert c4.calls == 1
    assert sequence.calls == 1
    assert api.calls == 0
    assert len(reporter.reports) == 1
    assert [outcome.name for outcome in reporter.reports[0]] == [
        StageId.C4,
        StageId.SEQUENCE,
    ]
    assert reporter.reports[0][-1].status is StageStatus.FAILED


def test_partial_stage_does_not_fail_pipeline() -> None:
    stage = FakeStage(StageId.C4, StageStatus.PARTIAL, payload={"architecture": True})
    reporter = RecordingReporter()

    assert _run([stage], reporter) == 0
    assert reporter.reports[0][0].status is StageStatus.PARTIAL


def _context(
    outcome: StageOutcome[object] | None = None,
) -> StageContext:
    upstream = {} if outcome is None else {outcome.name: outcome}
    return StageContext(
        scenario=_scenario(),
        out_dir=Path("output"),
        writer=InMemoryWriter(),
        upstream=upstream,
    )


def test_require_payload_accepts_succeeded_or_partial_typed_payload() -> None:
    for status in (StageStatus.SUCCEEDED, StageStatus.PARTIAL):
        outcome = StageOutcome(
            name=StageId.C4,
            status=status,
            duration_seconds=0.1,
            total_tokens=0,
            payload={"ready": True},
        )

        payload = require_payload(_context(outcome), StageId.C4, dict)

        assert payload == {"ready": True}


def test_require_payload_rejects_missing_failed_and_wrong_type_dependencies() -> None:
    with pytest.raises(PipelineDependencyError, match="Missing upstream stage"):
        require_payload(_context(), StageId.C4, dict)

    failed = StageOutcome(
        name=StageId.C4,
        status=StageStatus.FAILED,
        duration_seconds=0.1,
        total_tokens=0,
        payload={"ready": False},
    )
    with pytest.raises(PipelineDependencyError, match="failed; cannot consume its payload"):
        require_payload(_context(failed), StageId.C4, dict)

    success = StageOutcome(
        name=StageId.C4,
        status=StageStatus.SUCCEEDED,
        duration_seconds=0.1,
        total_tokens=0,
        payload="wrong-type",
    )
    with pytest.raises(PipelineDependencyError, match="expected dict"):
        require_payload(_context(success), StageId.C4, dict)
