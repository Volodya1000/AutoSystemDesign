import json
from pathlib import Path
from typing import Any

import pytest

from domain.document_requirements import (
    DocumentRequirements,
    Requirement,
    RequirementEvidence,
    RequirementKind,
)
from scripts import extract_document_requirements as cli


def _dummy_factory(*_args: object, **_kwargs: object) -> object:
    """Return an inert object for dependencies unused by the CLI test."""
    return object()


@pytest.mark.unit
def test_main_writes_serialized_extraction_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = tmp_path / "spec.md"
    document.write_text("The service supports login.", encoding="utf-8")
    output = tmp_path / "nested" / "result.json"
    expected = DocumentRequirements(
        requirements=[
            Requirement(
                statement="The service supports login.",
                kind=RequirementKind.FUNCTIONAL,
                source_evidence=[
                    RequirementEvidence(source_excerpt="The service supports login.")
                ],
            )
        ],
        is_relevant=True,
        source_name=document.name,
    )

    class FakeService:
        def __init__(self, reader: Any, extractor: Any) -> None:
            pass

        def extract_file(self, path: Path) -> DocumentRequirements:
            assert path == document
            return expected

    monkeypatch.setattr(cli, "load_app_settings", object)
    monkeypatch.setattr(cli, "LlmDocumentRequirementExtractor", _dummy_factory)
    monkeypatch.setattr(cli, "DocumentRequirementsService", FakeService)

    exit_code = cli.main(["--document", str(document), "--output", str(output)])

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["requirements"][0]["source_evidence"][0]["source_excerpt"] == (
        "The service supports login."
    )
