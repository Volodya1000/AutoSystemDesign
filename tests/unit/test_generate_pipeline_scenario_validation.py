"""Test CLI diagnostics for invalid YAML scenarios."""

import argparse
import logging
from pathlib import Path

import pytest

from scripts import generate_pipeline as cli

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("yaml_body", "invalid_location"),
    [
        ("requrements: []", "requrements"),
        ("worklod: {}", "worklod"),
        (
            """workload:
  baseline_requests_per_second: 10
  peak_requests_per_second: 20
  read_rato: 0.6""",
            "workload.read_rato",
        ),
    ],
)
def test_cli_reports_invalid_yaml_field_before_generation(
    yaml_body: str,
    invalid_location: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Reject invalid scenarios with code 2 and report the field path."""
    scenario_path = tmp_path / "broken.yaml"
    scenario_path.write_text(
        f"description: A valid scenario\n{yaml_body}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "configure_logging", lambda **_kwargs: None)
    monkeypatch.setattr(cli, "load_app_settings", lambda: object())
    monkeypatch.setattr(
        cli,
        "_parse_args",
        lambda: argparse.Namespace(scenario=str(scenario_path), verbose=False),
    )

    def unexpected_pipeline(**_kwargs: object) -> None:
        pytest.fail("Pipeline must not start for an invalid scenario")

    monkeypatch.setattr(cli, "build_pipeline", unexpected_pipeline)

    with caplog.at_level(logging.ERROR, logger="pipeline"):
        exit_code = cli.main()

    assert exit_code == 2
    assert str(scenario_path) in caplog.text
    assert f"at '{invalid_location}': Unknown field" in caplog.text
