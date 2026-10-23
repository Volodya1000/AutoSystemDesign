"""Test the future simulation output contract without running SimPy."""

import json

import pytest
from pydantic import ValidationError

from domain.architecture_simulation.configuration import SimulationConfiguration
from domain.architecture_simulation.report import (
    ConfidenceInterval,
    LatencyQuantiles,
    NodeSimulationMetrics,
    RequirementEvaluation,
    RequirementKind,
    RequirementVerdict,
    SimulationExperiment,
    SimulationFinding,
    SimulationFindingCode,
    SimulationLimitation,
    SimulationLimitationCode,
    SimulationReasonCode,
    SimulationReport,
    SimulationReportStatus,
    SimulationWorkload,
)

pytestmark = pytest.mark.unit


def _peak_experiment() -> SimulationExperiment:
    return SimulationExperiment(
        workload_id=SimulationWorkload.PEAK,
        offered_requests_per_second=60.0,
        generated_requests=5,
        completed_requests=3,
        rejected_requests=1,
        unfinished_requests=1,
        client_latency_milliseconds=LatencyQuantiles(p50=100, p95=200, p99=300),
        throughput_requests_per_second=30.0,
        nodes=[NodeSimulationMetrics(node_identifier="orders_db")],
    )


def test_full_report_round_trips_json() -> None:
    report = SimulationReport(
        scenario_identifier="checkout_baseline",
        status=SimulationReportStatus.PARTIAL,
        experiments=[_peak_experiment()],
        requirements=[
            RequirementEvaluation(
                requirement_index=1,
                type_identifier=RequirementKind.AVAILABILITY,
                phase=SimulationWorkload.PEAK,
                threshold_value=99.9,
                status=RequirementVerdict.NOT_EVALUATED,
                reason_code=SimulationReasonCode.FAILURE_REPAIR_MODEL_MISSING,
            )
        ],
        findings=[
            SimulationFinding(
                code=SimulationFindingCode.QUEUE_BOTTLENECK,
                severity="warning",
                title="Database queue",
                description="Model detects a waiting queue.",
            )
        ],
        limitations=[
            SimulationLimitation(
                code=SimulationLimitationCode.MODELED_NOT_MEASURED,
                description="Metrics are modeled, not measured.",
            )
        ],
    )

    restored = SimulationReport.model_validate_json(report.model_dump_json())

    assert restored == report
    assert restored.experiments[0].client_latency_milliseconds.p99 == 300.0


def test_unavailable_report_keeps_null_distinct_from_zero() -> None:
    report = SimulationReport(
        scenario_identifier="no_workload", status=SimulationReportStatus.UNAVAILABLE
    )

    payload = json.loads(report.model_dump_json())

    assert payload["experiments"] == []
    assert payload["requirements"] == []
    assert payload["configuration"]["warmup_seconds"] == 300.0


def test_report_collections_are_not_shared() -> None:
    first = SimulationReport(
        scenario_identifier="a", status=SimulationReportStatus.PARTIAL
    )
    second = SimulationReport(
        scenario_identifier="b", status=SimulationReportStatus.PARTIAL
    )

    first.experiments.append(_peak_experiment())

    assert second.experiments == []


@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf")])
def test_invalid_latency_is_rejected(value: float) -> None:
    with pytest.raises(ValidationError):
        LatencyQuantiles(p50=value)


@pytest.mark.parametrize(
    ("p50", "p95", "p99"),
    [(200.0, 100.0, None), (None, 200.0, 100.0), (200.0, None, 100.0)],
)
def test_percentiles_must_be_monotonic(
    p50: float | None, p95: float | None, p99: float | None
) -> None:
    with pytest.raises(ValidationError):
        LatencyQuantiles(p50=p50, p95=p95, p99=p99)


def test_generated_root_requests_must_be_accounted_for() -> None:
    with pytest.raises(ValidationError, match="root request outcomes"):
        SimulationExperiment(
            workload_id=SimulationWorkload.BASELINE,
            offered_requests_per_second=10,
            generated_requests=5,
            completed_requests=3,
            rejected_requests=1,
            unfinished_requests=0,
        )


def test_unmodeled_availability_cannot_claim_an_observation() -> None:
    with pytest.raises(ValidationError, match="unsupported requirement"):
        RequirementEvaluation(
            requirement_index=0,
            type_identifier=RequirementKind.AVAILABILITY,
            phase=SimulationWorkload.PEAK,
            threshold_value=99.9,
            status=RequirementVerdict.NOT_EVALUATED,
            observed_value=100,
            reason_code=SimulationReasonCode.FAILURE_REPAIR_MODEL_MISSING,
        )


def test_met_verdict_requires_uncertainty_interval() -> None:
    with pytest.raises(ValidationError, match="requires observed value and CI"):
        RequirementEvaluation(
            requirement_index=0,
            type_identifier=RequirementKind.LATENCY,
            phase=SimulationWorkload.PEAK,
            threshold_value=450,
            percentile=99,
            observed_value=420,
            status=RequirementVerdict.MET,
        )


def test_conclusive_verdict_with_evidence_round_trips() -> None:
    result = RequirementEvaluation(
        requirement_index=0,
        type_identifier=RequirementKind.LATENCY,
        phase=SimulationWorkload.PEAK,
        threshold_value=450,
        percentile=99,
        observed_value=420,
        status=RequirementVerdict.MET,
        confidence_interval=ConfidenceInterval(
            lower=0.995,
            upper=0.999,
            confidence_level=0.95,
            method="independent_replications",
        ),
    )

    assert RequirementEvaluation.model_validate_json(result.model_dump_json()) == result


def test_confidence_interval_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="lower bound"):
        ConfidenceInterval(lower=0.9, upper=0.8, confidence_level=0.95, method="test")


def test_report_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        SimulationReport.model_validate(
            {"scenario_identifier": "sample", "status": "partial", "wrong": True}
        )


def test_configuration_rejects_missing_or_invalid_duration() -> None:
    with pytest.raises(ValidationError):
        SimulationConfiguration(measurement_seconds=0)


def test_configuration_is_stable_json_contract() -> None:
    configuration = SimulationConfiguration(base_seed=0, replications=1)

    assert (
        SimulationConfiguration.model_validate_json(configuration.model_dump_json())
        == configuration
    )


def test_no_unrecognized_model_version() -> None:
    with pytest.raises(ValidationError):
        SimulationReport.model_validate(
            {"scenario_identifier": "x", "status": "partial", "model_version": "x"}
        )
