"""Shared isolation for all unit tests: hermetic, no repo config files."""

import os
from pathlib import Path

import pytest

from config.root import CONFIG_FILE_ENV_VAR


@pytest.fixture(autouse=True)
def isolated_unit_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Run every unit test without ASD_* env vars and outside the repo cwd.

    The chdir guarantees that neither .env nor config.yaml /
    config.test.yaml from the repository is picked up by settings sources.
    """
    for name in list(os.environ):
        if name.startswith("ASD_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv(CONFIG_FILE_ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)
