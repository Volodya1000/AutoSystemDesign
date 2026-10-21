"""Export or verify the published JSON Schema for the performance report."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from domain.performance_analysis.report import PerformanceAnalysisReport

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "performance-analysis"
    / "report.schema.json"
)
_logger = logging.getLogger("performance.schema")


def _schema_json() -> str:
    """Serialize the canonical model JSON Schema deterministically."""
    schema = PerformanceAnalysisReport.model_json_schema(mode="validation")
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    """Write on explicit request or verify the committed schema is current."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Regenerate the published schema from the canonical Pydantic model",
    )
    args = parser.parse_args()
    expected = _schema_json()

    if args.write:
        _SCHEMA_PATH.write_text(expected, encoding="utf-8")
        _logger.info("Schema updated: %s", _SCHEMA_PATH)
        return 0

    if not _SCHEMA_PATH.is_file():
        _logger.error("Schema file is missing: %s", _SCHEMA_PATH)
        return 1
    if _SCHEMA_PATH.read_text(encoding="utf-8") != expected:
        _logger.error("Published schema is stale. Run with --write to regenerate.")
        return 1
    _logger.info("Published schema matches the Pydantic contract")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
